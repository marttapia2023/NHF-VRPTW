"""Shared data loading, formulation, and reporting for the heterogeneous VRPTW."""

from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class VehicleType:
    name: str
    capacity: float
    fixed_cost: float
    distance_cost: float


@dataclass(frozen=True)
class Customer:
    node: int
    x: float
    y: float
    demand: float
    ready: float
    due: float
    service: float


@dataclass(frozen=True)
class Instance:
    name: str
    depot: int
    customers: tuple[Customer, ...]
    depot_ready: float
    depot_due: float
    fleet_size: int
    distances: dict[tuple[int, int], float]

    @property
    def nodes(self) -> tuple[int, ...]:
        return (self.depot, *(customer.node for customer in self.customers))

    @property
    def customer_by_node(self) -> dict[int, Customer]:
        return {customer.node: customer for customer in self.customers}


@dataclass(frozen=True)
class Variable:
    name: str
    lower: float
    upper: float
    kind: str
    objective: float


@dataclass(frozen=True)
class Constraint:
    name: str
    terms: tuple[tuple[str, float], ...]
    sense: str
    rhs: float


@dataclass(frozen=True)
class ModelSpec:
    variables: tuple[Variable, ...]
    constraints: tuple[Constraint, ...]
    arc_variables: dict[tuple[int, int, int], str]
    fleet_variables: dict[int, str]


DEFAULT_VEHICLE_TYPES = "van:100:100:1,truck:200:180:1"


def parse_vehicle_types(value: str) -> tuple[VehicleType, ...]:
    result: list[VehicleType] = []
    for item in value.split(","):
        fields = item.strip().split(":")
        if len(fields) not in (3, 4):
            raise argparse.ArgumentTypeError(
                "Cada tipo debe tener el formato "
                "nombre:capacidad:costo_fijo[:costo_por_distancia]"
            )
        name, capacity_text, fixed_cost_text = fields[:3]
        distance_cost_text = fields[3] if len(fields) == 4 else "1"
        try:
            capacity = float(capacity_text)
            fixed_cost = float(fixed_cost_text)
            distance_cost = float(distance_cost_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Capacidad y costos deben ser números: {item}"
            ) from exc
        if not name or not math.isfinite(capacity) or capacity <= 0:
            raise argparse.ArgumentTypeError(
                f"Nombre no vacío y capacidad positiva requeridos: {item}"
            )
        if not math.isfinite(fixed_cost) or fixed_cost < 0:
            raise argparse.ArgumentTypeError(
                f"El costo fijo debe ser un número no negativo: {item}"
            )
        if not math.isfinite(distance_cost) or distance_cost < 0:
            raise argparse.ArgumentTypeError(
                f"El costo por unidad de distancia debe ser un número no negativo: {item}"
            )
        result.append(VehicleType(name, capacity, fixed_cost, distance_cost))
    if not result:
        raise argparse.ArgumentTypeError("Debe especificarse al menos un tipo de vehículo")
    if len({vehicle.name for vehicle in result}) != len(result):
        raise argparse.ArgumentTypeError("Los nombres de los tipos deben ser únicos")
    return tuple(result)


def parse_vehicle_availability(value: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in value.split(","):
        fields = item.strip().split(":")
        if len(fields) != 2 or not fields[0].strip():
            raise argparse.ArgumentTypeError(
                "Cada disponibilidad debe tener el formato nombre:cantidad"
            )
        name, count_text = fields[0].strip(), fields[1].strip()
        try:
            count = int(count_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"La cantidad disponible debe ser un entero no negativo: {item}"
            ) from exc
        if count < 0:
            raise argparse.ArgumentTypeError(
                f"La cantidad disponible debe ser un entero no negativo: {item}"
            )
        if name in result:
            raise argparse.ArgumentTypeError(
                f"Disponibilidad repetida para el tipo de vehículo {name}"
            )
        result[name] = count
    if not result:
        raise argparse.ArgumentTypeError("Debe indicarse al menos un tipo de vehículo")
    return result


def load_instance(path: Path, service_time_scale: float = 1.0) -> Instance:
    if not math.isfinite(service_time_scale) or service_time_scale <= 0:
        raise ValueError("service_time_scale debe ser un número positivo")

    root = ET.parse(path).getroot()
    coordinates: dict[int, tuple[float, float]] = {}
    depot_candidates: list[int] = []
    for node in root.findall("./network/nodes/node"):
        node_id = int(node.attrib["id"])
        coordinates[node_id] = (
            float(node.findtext("cx", "0")),
            float(node.findtext("cy", "0")),
        )
        if node.attrib.get("type") == "0":
            depot_candidates.append(node_id)
    if len(depot_candidates) != 1:
        raise ValueError(f"{path}: se esperaba un único depósito, se encontraron {len(depot_candidates)}")
    depot = depot_candidates[0]

    customers: list[Customer] = []
    for request in root.findall("./requests/request"):
        node_id = int(request.attrib["node"])
        if node_id == depot:
            continue
        if node_id not in coordinates:
            raise ValueError(f"{path}: solicitud asociada a un nodo inexistente ({node_id})")
        time_window = request.find("tw")
        if time_window is None:
            raise ValueError(f"{path}: falta la ventana de tiempo del nodo {node_id}")
        customer = Customer(
            node=node_id,
            x=coordinates[node_id][0],
            y=coordinates[node_id][1],
            demand=float(request.findtext("quantity", "0")),
            ready=float(time_window.findtext("start", "0")),
            due=float(time_window.findtext("end", "0")),
            service=float(request.findtext("service_time", "0")) * service_time_scale,
        )
        if customer.demand < 0 or customer.ready > customer.due or customer.service < 0:
            raise ValueError(f"{path}: datos inválidos en la solicitud del nodo {node_id}")
        customers.append(customer)
    if not customers:
        raise ValueError(f"{path}: no se encontraron clientes")

    profile = root.find("./fleet/vehicle_profile")
    if profile is None:
        raise ValueError(f"{path}: falta fleet/vehicle_profile")
    fleet_size = int(profile.attrib.get("number", "0"))
    if fleet_size <= 0:
        raise ValueError(f"{path}: el tamaño de flota debe ser positivo")
    depot_ready = 0.0
    depot_due = max(
        float(profile.findtext("max_travel_time", "0")),
        max(customer.due for customer in customers),
    )
    if depot_due <= depot_ready:
        raise ValueError(f"{path}: horizonte del depósito inválido")

    nodes = (depot, *(customer.node for customer in customers))
    distances = {
        (i, j): math.hypot(
            coordinates[i][0] - coordinates[j][0],
            coordinates[i][1] - coordinates[j][1],
        )
        for i in nodes
        for j in nodes
        if i != j
    }
    return Instance(
        name=root.findtext("./info/name", path.stem),
        depot=depot,
        customers=tuple(customers),
        depot_ready=depot_ready,
        depot_due=depot_due,
        fleet_size=fleet_size,
        distances=distances,
    )


def build_model(
    instance: Instance,
    vehicle_types: tuple[VehicleType, ...],
    vehicle_availability: dict[str, int] | None = None,
) -> ModelSpec:
    variables: list[Variable] = []
    constraints: list[Constraint] = []
    arc_variables: dict[tuple[int, int, int], str] = {}
    fleet_variables: dict[int, str] = {}
    customers = instance.customers
    depot = instance.depot
    nodes = instance.nodes
    count = len(customers)
    max_distance = max(instance.distances.values())
    max_service = max(customer.service for customer in customers)
    big_m = max(
        1.0,
        instance.depot_due - instance.depot_ready + max_distance + max_service,
    )

    def add_variable(name: str, lower: float, upper: float, kind: str, objective: float = 0.0) -> None:
        variables.append(Variable(name, lower, upper, kind, objective))

    def add_constraint(name: str, terms: dict[str, float], sense: str, rhs: float) -> None:
        constraints.append(
            Constraint(
                name,
                tuple((variable, coefficient) for variable, coefficient in terms.items() if coefficient),
                sense,
                rhs,
            )
        )

    inbound: dict[tuple[int, int], list[str]] = {}
    outbound: dict[tuple[int, int], list[str]] = {}
    for k, vehicle in enumerate(vehicle_types):
        for i in nodes:
            for j in nodes:
                if i == j:
                    continue
                name = f"x_{k}_{i}_{j}"
                arc_variables[k, i, j] = name
                add_variable(
                    name,
                    0,
                    1,
                    "B",
                    instance.distances[i, j] * vehicle.distance_cost,
                )
                inbound.setdefault((k, j), []).append(name)
                outbound.setdefault((k, i), []).append(name)
                if j != depot:
                    flow_name = f"f_{k}_{i}_{j}"
                    add_variable(flow_name, 0, vehicle.capacity, "C")
                    add_constraint(
                        f"flow_capacity_{k}_{i}_{j}",
                        {flow_name: 1, name: -vehicle.capacity},
                        "L",
                        0,
                    )

        for customer in customers:
            i = customer.node
            time_name = f"t_{k}_{i}"
            order_name = f"u_{k}_{i}"
            add_variable(time_name, customer.ready, customer.due, "C")
            add_variable(order_name, 1, count, "C")

        fleet_name = f"y_{k}"
        fleet_variables[k] = fleet_name
        available = (
            vehicle_availability.get(vehicle.name, instance.fleet_size)
            if vehicle_availability is not None
            else instance.fleet_size
        )
        add_variable(
            fleet_name,
            0,
            min(instance.fleet_size, available),
            "I",
            vehicle.fixed_cost,
        )

    for customer in customers:
        node = customer.node
        add_constraint(
            f"customer_in_{node}",
            {arc_variables[k, i, node]: 1 for k in range(len(vehicle_types)) for i in nodes if i != node},
            "E",
            1,
        )
        add_constraint(
            f"customer_out_{node}",
            {arc_variables[k, node, j]: 1 for k in range(len(vehicle_types)) for j in nodes if j != node},
            "E",
            1,
        )

    for k, vehicle in enumerate(vehicle_types):
        for customer in customers:
            node = customer.node
            flow_terms: dict[str, float] = {}
            for i in nodes:
                if i != node:
                    flow_terms[f"f_{k}_{i}_{node}"] = 1
            for j in customers:
                if j.node != node:
                    flow_terms[f"f_{k}_{node}_{j.node}"] = -1
            for i in nodes:
                if i != node:
                    flow_terms[arc_variables[k, i, node]] = -customer.demand
            add_constraint(f"load_balance_{k}_{node}", flow_terms, "E", 0)

            degree_terms = {name: 1 for name in inbound[k, node]}
            degree_terms.update({name: -1 for name in outbound[k, node]})
            add_constraint(f"vehicle_flow_{k}_{node}", degree_terms, "E", 0)

        start_terms = {arc_variables[k, depot, customer.node]: 1 for customer in customers}
        start_terms[fleet_variables[k]] = -1
        add_constraint(f"route_start_{k}", start_terms, "E", 0)
        end_terms = {arc_variables[k, customer.node, depot]: 1 for customer in customers}
        end_terms[fleet_variables[k]] = -1
        add_constraint(f"route_end_{k}", end_terms, "E", 0)

        for customer in customers:
            i = customer.node
            for next_customer in customers:
                j = next_customer.node
                if i == j:
                    continue
                x_name = arc_variables[k, i, j]
                add_constraint(
                    f"time_{k}_{i}_{j}",
                    {f"t_{k}_{j}": 1, f"t_{k}_{i}": -1, x_name: -big_m},
                    "G",
                    customer.service + instance.distances[i, j] - big_m,
                )
                add_constraint(
                    f"order_{k}_{i}_{j}",
                    {f"u_{k}_{j}": 1, f"u_{k}_{i}": -1, x_name: -count},
                    "G",
                    1 - count,
                )
            depot_arc = arc_variables[k, depot, i]
            add_constraint(
                f"time_from_depot_{k}_{i}",
                {f"t_{k}_{i}": 1, depot_arc: -big_m},
                "G",
                instance.depot_ready + instance.distances[depot, i] - big_m,
            )
            return_arc = arc_variables[k, i, depot]
            add_constraint(
                f"time_to_depot_{k}_{i}",
                {f"t_{k}_{i}": 1, return_arc: big_m},
                "L",
                instance.depot_due - customer.service - instance.distances[i, depot] + big_m,
            )

    add_constraint(
        "fleet_limit",
        {name: 1 for name in fleet_variables.values()},
        "L",
        instance.fleet_size,
    )
    return ModelSpec(tuple(variables), tuple(constraints), arc_variables, fleet_variables)


def add_common_arguments(parser: argparse.ArgumentParser, solver: str) -> None:
    parser.add_argument("--instance", required=True, type=Path, help="Archivo XML de una instancia Solomon")
    parser.add_argument(
        "--vehicle-types",
        type=parse_vehicle_types,
        default=parse_vehicle_types(DEFAULT_VEHICLE_TYPES),
        metavar="TIPOS",
        help=(
            "Tipos en formato nombre:capacidad:costo_fijo:costo_distancia "
            "separados por comas "
            f"(default: {DEFAULT_VEHICLE_TYPES})"
        ),
    )
    parser.add_argument(
        "--vehicle-availability",
        type=parse_vehicle_availability,
        metavar="DISPONIBILIDAD",
        help=(
            "Máximo disponible por tipo, con formato nombre:cantidad y "
            "separados por comas; al usarlo, debe incluir todos los tipos"
        ),
    )
    parser.add_argument("--time-limit", type=float, default=3600, help="Límite de tiempo en segundos (default: 3600)")
    parser.add_argument("--mip-gap", type=float, default=1e-4, help="Tolerancia relativa MIP (default: 0.0001)")
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria")
    parser.add_argument("--threads", type=int, default=0, help="Hilos del solver (0: automático)")
    parser.add_argument(
        "--service-time-scale",
        type=float,
        default=1.0,
        help="Factor multiplicativo para service_time del XML (default: 1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"Ruta del JSON de resultados (default: Resultados/{solver}/<instancia>.json)",
    )


def validate_arguments(args: argparse.Namespace) -> None:
    if args.time_limit <= 0 or not math.isfinite(args.time_limit):
        raise ValueError("--time-limit debe ser positivo")
    if not 0 <= args.mip_gap < 1 or not math.isfinite(args.mip_gap):
        raise ValueError("--mip-gap debe estar entre 0 (inclusive) y 1 (exclusive)")
    if args.threads < 0:
        raise ValueError("--threads no puede ser negativo")
    if args.vehicle_availability is not None:
        vehicle_names = {vehicle.name for vehicle in args.vehicle_types}
        availability_names = set(args.vehicle_availability)
        if availability_names != vehicle_names:
            missing = sorted(vehicle_names - availability_names)
            extra = sorted(availability_names - vehicle_names)
            details = []
            if missing:
                details.append(f"faltan tipos: {', '.join(missing)}")
            if extra:
                details.append(f"tipos desconocidos: {', '.join(extra)}")
            raise ValueError(
                "--vehicle-availability debe incluir exactamente los tipos "
                "definidos en --vehicle-types (" + "; ".join(details) + ")"
            )


def extract_routes(
    instance: Instance,
    vehicle_types: tuple[VehicleType, ...],
    spec: ModelSpec,
    values: dict[str, float],
) -> list[dict[str, object]]:
    routes: list[dict[str, object]] = []
    for k, vehicle in enumerate(vehicle_types):
        successors: dict[int, int] = {}
        starts: list[int] = []
        for (arc_k, i, j), name in spec.arc_variables.items():
            if arc_k == k and values.get(name, 0) > 0.5:
                successors[i] = j
                if i == instance.depot:
                    starts.append(j)
        for start in starts:
            route = [instance.depot, start]
            current = start
            seen = {instance.depot}
            while current != instance.depot and current not in seen:
                seen.add(current)
                if current not in successors:
                    break
                current = successors[current]
                route.append(current)
            if route[-1] != instance.depot:
                continue
            customers = instance.customer_by_node
            routes.append(
                {
                    "vehicle_type": vehicle.name,
                    "nodes": route,
                    "demand": sum(customers[node].demand for node in route if node in customers),
                    "distance": sum(
                        instance.distances[i, j] for i, j in zip(route, route[1:])
                    ),
                    "distance_cost_per_unit": vehicle.distance_cost,
                    "travel_cost": vehicle.distance_cost
                    * sum(instance.distances[i, j] for i, j in zip(route, route[1:])),
                    "fixed_cost": vehicle.fixed_cost,
                }
            )
    return routes


def save_result(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None
