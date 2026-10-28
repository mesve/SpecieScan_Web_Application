# SpecieScan Reference Databases (2024)

These are the default reference databases bundled with SpecieScan. They come
from the SpecieScan algorithm and were last updated in 2024.

Source set: `Reference Databases 2023-11-13` (files updated February 2024).

| File | Menu label | Species rows |
|---|---|---|
| `Mammals_reference_Eurasia.csv` | Eurasia Mammals | 121 |
| `Mammals_reference_Africa.csv` | African Mammals | 65 |
| `Mammals_reference_new_world.csv` | New World Mammals | 97 |
| `Bird_reference_db.csv` | Birds | 21 |
| `Fish_reference_db_1.csv` | Fish | 141 |
| `Amphibians_reference_db.csv` | Amphibians | 11 |
| `Reptiles_reference_db.csv` | Reptiles | 8 |

## Layout

Every database has the same four metadata columns followed by marker-mass
columns:

```
Order, Family, Species, ZooMS_taxon, <marker 1>, <marker 2>, ...
```

Blank marker cells are allowed. A marker cell normally contains one mass, but
the Fish database contains cells with alternative masses such as
`1600/ 1588` or `2450/2541`. The application treats those as one marker
position that matches if any listed mass is within the matching tolerance.

## Custom databases

Users can upload their own CSV from Step 9. A custom database must:

- be a `.csv` file,
- contain the columns `Order`, `Family`, `Species`, and `ZooMS_taxon`,
- contain at least one marker-mass column,
- use numeric values (one or more masses per cell, separated by `/`, `•`, or
  whitespace).
