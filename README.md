# NHF-VRPTW

Proyecto de optimización del problema de ruteo de vehículos con ventanas de
tiempo y capacidad (VRPTW), con flota heterogénea y comparación entre Gurobi y
CPLEX.

## Modelo implementado

El objetivo minimiza la distancia euclidiana total más el costo fijo de cada
vehículo utilizado. Se permiten varios tipos de vehículos; cada tipo tiene su
propia capacidad y costo fijo. La formulación incluye cobertura de clientes,
conservación de flujo, capacidad mediante flujo de carga, ventanas de tiempo,
eliminación de subrutas y un límite total de vehículos igual al disponible en
la instancia Solomon. Los tiempos de viaje son iguales a las distancias
euclidianas, como en la formulación base de Solomon; el depósito abre en 0 y su
cierre se toma del horizonte de viaje o de la ventana más tardía.

Solomon no proporciona costos fijos ni capacidades para una flota heterogénea.
Por ello, los valores predeterminados son un escenario configurable para el
proyecto:

| Tipo predeterminado | Capacidad | Costo fijo | Costo por distancia |
|---|---:|---:|---:|
| van | 100 | 100 | 1 |
| truck | 200 | 180 | 1 |

El cuarto parámetro permite diferenciar el costo por unidad de distancia de
cada tipo. El objetivo es `suma_k (costo_fijo_k * vehículos_usados_k) + suma_kij
(costo_distancia_k * distancia_ij * x_kij)`. El valor 1 conserva el
comportamiento anterior, donde una unidad de distancia cuesta lo mismo para
todos los camiones. Ajuste capacidades y costos con datos de la organización o
con el escenario que el equipo documente en su informe.

## Requisitos

Instale Python 3, la API oficial de cada solver y una licencia válida:

- Gurobi: `gurobipy`
- IBM ILOG CPLEX: `cplex`

`vrptw_common.py` construye la formulación algebraica compartida; los dos
ejecutables usan las mismas variables, restricciones y valores de parámetros.
Las licencias Community de los solvers pueden imponer límites de tamaño; para
las instancias que los excedan se requiere ejecutar con licencias completas,
por ejemplo en el servidor Luthier.

## Ejecución

Desde la raíz del repositorio, ejecute cada solver con la misma instancia y
parámetros. Ejemplo reducido:

```powershell
python gurobi_vrptw.py --instance "Instancias\Solomon\solomon-1987-c1\C101_025.xml" --time-limit 3600 --seed 42 --mip-gap 0.0001
python cplex_vrptw.py --instance "Instancias\Solomon\solomon-1987-c1\C101_025.xml" --time-limit 3600 --seed 42 --mip-gap 0.0001
```

Configure otros tipos de flota con el formato
`nombre:capacidad:costo_fijo:costo_por_unidad_de_distancia`, separados por
comas:

```powershell
python gurobi_vrptw.py --instance "Instancias\Solomon\solomon-1987-c1\C101_025.xml" --vehicle-types "furgon:80:70:0.8,camion:200:180:1.35"
```

El costo por distancia es opcional: el formato anterior de tres campos
`nombre:capacidad:costo_fijo` sigue siendo válido y asume costo unitario 1.
Use los mismos valores de `--vehicle-types` al comparar Gurobi y CPLEX. Los
JSON registran el costo unitario de cada tipo y el costo de viaje de cada ruta.

Ambos programas usan por defecto un límite de 3600 segundos, semilla 42,
brecha MIP relativa de 0.0001 y todos los hilos disponibles. La instancia y
los resultados se guardan en JSON en `Resultados\gurobi` y `Resultados\CPLEX`,
respectivamente. El JSON contiene el estado, objetivo/incumbente, mejor cota,
MIPgap porcentual, tiempos de pared y CPU del proceso, parámetros de ejecución
y rutas.

Los XML de este repositorio se leen directamente: coordenadas, demandas,
ventanas de tiempo, tiempos de servicio y disponibilidad de flota provienen de
los archivos. Si se requiere transformar unidades de servicio, ambos
ejecutables aceptan `--service-time-scale` con el mismo factor.
