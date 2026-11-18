"""Solve the heterogeneous Solomon VRPTW with the official Gurobi Python API."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from vrptw_common import (
    add_common_arguments,
    build_model,
    extract_routes,
    finite_or_none,
    load_instance,
    save_result,
    validate_arguments,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser, "gurobi")
    args = parser.parse_args()
    try:
        validate_arguments(args)
        instance = load_instance(args.instance, args.service_time_scale)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    try:
        import gurobipy as gp
    except ImportError:
        print("No se encontró gurobipy. Instale la API oficial de Gurobi.", file=sys.stderr)
        return 2

    spec = build_model(instance, args.vehicle_types)
    model = gp.Model(f"heterogeneous_vrptw_{instance.name}")
    model.Params.TimeLimit = args.time_limit
    model.Params.MIPGap = args.mip_gap
    model.Params.Seed = args.seed
    model.Params.Threads = args.threads
    model.ModelSense = gp.GRB.MINIMIZE
    variables = {}
    for variable in spec.variables:
        kind = {"B": gp.GRB.BINARY, "I": gp.GRB.INTEGER, "C": gp.GRB.CONTINUOUS}[variable.kind]
        variables[variable.name] = model.addVar(
            lb=variable.lower,
            ub=variable.upper,
            obj=variable.objective,
            vtype=kind,
            name=variable.name,
        )
    model.update()
    for row in spec.constraints:
        expression = gp.quicksum(coefficient * variables[name] for name, coefficient in row.terms)
        if row.sense == "E":
            model.addConstr(expression == row.rhs, name=row.name)
        elif row.sense == "L":
            model.addConstr(expression <= row.rhs, name=row.name)
        else:
            model.addConstr(expression >= row.rhs, name=row.name)

    started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        model.optimize()
    except gp.GurobiError as exc:
        print(f"Gurobi no pudo resolver la instancia: {exc}", file=sys.stderr)
        return 2
    elapsed = time.perf_counter() - started
    cpu_elapsed = time.process_time() - cpu_started
    has_solution = model.SolCount > 0
    value_map = {name: variable.X for name, variable in variables.items()} if has_solution else {}
    status_names = {
        gp.GRB.OPTIMAL: "optimal",
        gp.GRB.TIME_LIMIT: "time_limit",
        gp.GRB.INFEASIBLE: "infeasible",
        gp.GRB.INF_OR_UNBD: "infeasible_or_unbounded",
        gp.GRB.UNBOUNDED: "unbounded",
        gp.GRB.INTERRUPTED: "interrupted",
        gp.GRB.SUBOPTIMAL: "suboptimal",
    }
    bound_available = model.Status not in {
        gp.GRB.INFEASIBLE,
        gp.GRB.INF_OR_UNBD,
        gp.GRB.UNBOUNDED,
    }
    result = {
        "solver": "gurobi",
        "instance": instance.name,
        "instance_path": str(args.instance.resolve()),
        "status": status_names.get(model.Status, f"status_{model.Status}"),
        "runtime_seconds": elapsed,
        "wall_time_seconds": elapsed,
        "cpu_time_seconds": cpu_elapsed,
        "solver_runtime_seconds": model.Runtime,
        "time_limit_seconds": args.time_limit,
        "mip_gap_tolerance": args.mip_gap,
        "seed": args.seed,
        "threads": args.threads,
        "vehicle_types": [
            {
                "name": vehicle.name,
                "capacity": vehicle.capacity,
                "fixed_cost": vehicle.fixed_cost,
                "distance_cost_per_unit": vehicle.distance_cost,
            }
            for vehicle in args.vehicle_types
        ],
        "objective": model.ObjVal if has_solution else None,
        "best_bound": finite_or_none(model.ObjBound) if bound_available else None,
        "mip_gap_percent": model.MIPGap * 100 if has_solution else None,
        "routes": extract_routes(instance, args.vehicle_types, spec, value_map) if has_solution else [],
    }
    output = args.output or Path("Resultados") / "gurobi" / f"{instance.name}.json"
    save_result(output, result)
    print(
        f"Gurobi: {result['status']} | objetivo={result['objective']} | "
        f"gap%={result['mip_gap_percent']} | tiempo={result['runtime_seconds']:.2f}s"
    )
    print(f"Resultados: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
