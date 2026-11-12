"""Solve the heterogeneous Solomon VRPTW with the official CPLEX Python API."""

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
    add_common_arguments(parser, "CPLEX")
    args = parser.parse_args()
    try:
        validate_arguments(args)
        instance = load_instance(args.instance, args.service_time_scale)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    try:
        import cplex
    except ImportError:
        print("No se encontró cplex. Instale la API oficial de IBM CPLEX.", file=sys.stderr)
        return 2

    spec = build_model(instance, args.vehicle_types)
    model = cplex.Cplex()
    model.set_problem_name(f"heterogeneous_vrptw_{instance.name}")
    model.objective.set_sense(model.objective.sense.minimize)
    model.parameters.timelimit.set(args.time_limit)
    model.parameters.mip.tolerances.mipgap.set(args.mip_gap)
    model.parameters.randomseed.set(args.seed)
    model.parameters.threads.set(args.threads)

    variable_names = [variable.name for variable in spec.variables]
    model.variables.add(
        obj=[variable.objective for variable in spec.variables],
        lb=[variable.lower for variable in spec.variables],
        ub=[variable.upper for variable in spec.variables],
        types=[variable.kind for variable in spec.variables],
        names=variable_names,
    )
    rows = [
        cplex.SparsePair(
            ind=[name for name, _ in row.terms],
            val=[coefficient for _, coefficient in row.terms],
        )
        for row in spec.constraints
    ]
    model.linear_constraints.add(
        lin_expr=rows,
        senses="".join(row.sense for row in spec.constraints),
        rhs=[row.rhs for row in spec.constraints],
        names=[row.name for row in spec.constraints],
    )

    started = time.perf_counter()
    cpu_started = time.process_time()
    try:
        model.solve()
    except cplex.exceptions.CplexSolverError as exc:
        print(f"CPLEX no pudo resolver la instancia: {exc}", file=sys.stderr)
        return 2
    elapsed = time.perf_counter() - started
    cpu_elapsed = time.process_time() - cpu_started
    has_solution = model.solution.is_primal_feasible()
    value_map = (
        dict(zip(variable_names, model.solution.get_values()))
        if has_solution
        else {}
    )
    status_text = model.solution.get_status_string()
    bound_available = "infeasible" not in status_text.lower() and "unbounded" not in status_text.lower()
    best_bound = model.solution.MIP.get_best_objective() if bound_available else None
    mip_gap = model.solution.MIP.get_mip_relative_gap() if has_solution else None
    result = {
        "solver": "cplex",
        "instance": instance.name,
        "instance_path": str(args.instance.resolve()),
        "status": status_text,
        "runtime_seconds": elapsed,
        "wall_time_seconds": elapsed,
        "cpu_time_seconds": cpu_elapsed,
        "solver_runtime_seconds": elapsed,
        "time_limit_seconds": args.time_limit,
        "mip_gap_tolerance": args.mip_gap,
        "seed": args.seed,
        "threads": args.threads,
        "vehicle_types": [
            {"name": vehicle.name, "capacity": vehicle.capacity, "fixed_cost": vehicle.fixed_cost}
            for vehicle in args.vehicle_types
        ],
        "objective": model.solution.get_objective_value() if has_solution else None,
        "best_bound": finite_or_none(best_bound) if best_bound is not None else None,
        "mip_gap_percent": mip_gap * 100 if mip_gap is not None else None,
        "routes": extract_routes(instance, args.vehicle_types, spec, value_map) if has_solution else [],
    }
    output = args.output or Path("Resultados") / "CPLEX" / f"{instance.name}.json"
    save_result(output, result)
    print(
        f"CPLEX: {result['status']} | objetivo={result['objective']} | "
        f"gap%={result['mip_gap_percent']} | tiempo={result['runtime_seconds']:.2f}s"
    )
    print(f"Resultados: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
