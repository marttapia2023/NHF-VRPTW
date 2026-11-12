## Validación inicial

`C101_005.xml` es una reducción reproducible de la instancia Solomon
`C101_025.xml`: conserva el depósito y los primeros cinco clientes, con sus
coordenadas, demandas, ventanas de tiempo y tiempos de servicio originales.

Gurobi y CPLEX se ejecutaron con la misma formulación y configuración:
semilla 42, un hilo, límite de 3600 segundos, brecha relativa objetivo de
0.0001 y flota predeterminada (`van:100:100,truck:200:180`).

Ambos encontraron el óptimo 142.41983891815494, con brecha 0 %, y asignaron los
cinco clientes a una van con carga 70. La ruta fue `0-5-3-4-2-1-0`; se
verificaron la cobertura de cada cliente y la capacidad del vehículo.

Resultados detallados:

- [Gurobi](../../Resultados/gurobi/C101_005.json)
- [CPLEX](../../Resultados/CPLEX/C101_005.json)
- [Resumen comparativo](../../Resultados/validacion_inicial.csv)
 