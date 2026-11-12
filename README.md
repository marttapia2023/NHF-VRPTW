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

| Tipo predeterminado | Capacidad | Costo fijo |
|---|---:|---:|
| van | 100 | 100 |
| truck | 200 | 180 |

El costo de distancia es 1 por unidad para todos los tipos. Ajuste los costos y
capacidades con los datos de la organización o con el escenario que el equipo
documente en su informe.

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
`nombre:capacidad:costo_fijo`, separados por comas:

```powershell
python gurobi_vrptw.py --instance "Instancias\Solomon\solomon-1987-c1\C101_025.xml" --vehicle-types "furgon:80:70,camion:200:180"
```

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
