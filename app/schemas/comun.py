from typing import Annotated

from fastapi import Path, Query
from pydantic import Field

# Los id son INTEGER en PostgreSQL: un número mayor hace fallar la consulta
# con un 500. Con estos límites la API responde 422 antes de llegar a la base.
ID_MAX = 2_147_483_647

Id = Annotated[int, Field(ge=1, le=ID_MAX)]
IdPath = Annotated[int, Path(ge=1, le=ID_MAX)]
IdQuery = Annotated[int | None, Query(ge=1, le=ID_MAX)]
