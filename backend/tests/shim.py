"""
Minimal stand-ins for fastapi / pydantic / sqlalchemy so that the REAL
app/routers/auth.py, app/deps.py, app/models.py and app/schemas.py can be
imported and called directly in this sandbox (no network = no pip install).

Only the slice of each API that the project actually uses is implemented.
"""
import datetime
import os
import sys
import types

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED = object()


# ===========================================================================
# sqlalchemy
# ===========================================================================
class Pred:
    """A row predicate, so filters can be combined with or_() / multiple args."""

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, row):
        return self.fn(row)

    def __or__(self, other):
        return Pred(lambda r: self(r) or other(r))

    def __and__(self, other):
        return Pred(lambda r: self(r) and other(r))


def or_(*preds):
    return Pred(lambda r: any(p(r) for p in preds))


class Col:
    """Stands in for sqlalchemy.Column on the class, and builds comparisons."""

    def __init__(self, *args, **kwargs):
        self.name = None
        self.default = kwargs.get("default")
        self.nullable = kwargs.get("nullable", True)

    def __set_name__(self, owner, name):
        if self.name is None:
            self.name = name

    def _get(self, row):
        return getattr(row, self.name, None)

    def __eq__(self, other):
        return Pred(lambda r: self._get(r) == other)

    def __ne__(self, other):
        return Pred(lambda r: self._get(r) != other)

    def ilike(self, pattern):
        needle = str(pattern).strip("%").lower()
        return Pred(lambda r: needle in str(self._get(r) or "").lower())

    def is_(self, other):
        return Pred(lambda r: self._get(r) is other)

    def desc(self):
        return ("desc", self.name)

    def asc(self):
        return ("asc", self.name)

    def __hash__(self):
        return id(self)


def Column(*args, **kwargs):
    # Support Column("db_name", Type, ...) aliasing used by Incident.action_plan_json
    return Col(*args, **kwargs)


def relationship(*args, **kwargs):
    return None


def ForeignKey(*args, **kwargs):
    return None


class _Type:
    def __init__(self, *a, **k):
        pass


Integer = String = Float = DateTime = Text = Boolean = _Type


def text(sql):
    return sql


def create_engine(*a, **k):
    return types.SimpleNamespace()


def declarative_base():
    class Base:
        def __init__(self, **kwargs):
            # Apply column defaults first, then the supplied values.
            for klass in type(self).__mro__:
                for key, val in vars(klass).items():
                    if isinstance(val, Col) and not hasattr(self, "_i_" + key):
                        default = val.default
                        if callable(default):
                            default = default()
                        object.__setattr__(self, key, default)
                        object.__setattr__(self, "_i_" + key, True)
            for key, val in kwargs.items():
                setattr(self, key, val)

        @classmethod
        def _columns(cls):
            names = []
            for klass in cls.__mro__:
                for key, val in vars(klass).items():
                    if isinstance(val, Col):
                        names.append(key)
            return names

    return Base


def sessionmaker(*a, **k):
    return lambda: None


_sa = types.ModuleType("sqlalchemy")
for _n in ("Column", "Integer", "String", "Float", "DateTime", "ForeignKey",
           "Text", "Boolean", "text", "create_engine", "or_"):
    setattr(_sa, _n, globals()[_n])
sys.modules["sqlalchemy"] = _sa

_sa_orm = types.ModuleType("sqlalchemy.orm")
_sa_orm.relationship = relationship
_sa_orm.sessionmaker = sessionmaker
_sa_orm.declarative_base = declarative_base
_sa_orm.Session = object
sys.modules["sqlalchemy.orm"] = _sa_orm


# ===========================================================================
# fastapi
# ===========================================================================
class HTTPException(Exception):
    def __init__(self, status_code, detail=None, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


class _Status:
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403
    HTTP_409_CONFLICT = 409
    HTTP_422_UNPROCESSABLE_ENTITY = 422


class APIRouter:
    def __init__(self, **kwargs):
        self.routes = {}

    def _register(self, method, path, **kw):
        def deco(fn):
            self.routes[(method, path)] = fn
            return fn
        return deco

    def get(self, path, **kw):
        return self._register("GET", path, **kw)

    def post(self, path, **kw):
        return self._register("POST", path, **kw)

    def put(self, path, **kw):
        return self._register("PUT", path, **kw)


def Depends(dependency=None):
    return dependency


def Header(default=None, **kwargs):
    return default


def Query(default=None, **kwargs):
    return None if default is ... else default


class StreamingResponse:
    def __init__(self, content, media_type=None, headers=None):
        self.body = content.read() if hasattr(content, "read") else content
        self.media_type = media_type
        self.headers = headers or {}


_fa = types.ModuleType("fastapi")
_fa.APIRouter = APIRouter
_fa.Depends = Depends
_fa.Header = Header
_fa.HTTPException = HTTPException
_fa.status = _Status
_fa.Query = Query
sys.modules["fastapi"] = _fa

_fa_resp = types.ModuleType("fastapi.responses")
_fa_resp.StreamingResponse = StreamingResponse
sys.modules["fastapi.responses"] = _fa_resp


# ===========================================================================
# pydantic
# ===========================================================================
def Field(default=REQUIRED, **kwargs):
    return default


class BaseModel:
    def __init__(self, **kwargs):
        ann = self._annotations()
        for name in ann:
            if name in kwargs:
                setattr(self, name, kwargs[name])
            else:
                default = getattr(type(self), name, REQUIRED)
                if default is REQUIRED:
                    raise ValueError(f"missing required field: {name}")
                setattr(self, name, default)

    @classmethod
    def _annotations(cls):
        out = {}
        for klass in reversed(cls.__mro__):
            out.update(getattr(klass, "__annotations__", {}))
        return out

    @classmethod
    def model_validate(cls, obj):
        data = {}
        for name in cls._annotations():
            if hasattr(obj, name):
                data[name] = getattr(obj, name)
        return cls(**data)

    def model_dump(self):
        return {n: getattr(self, n, None) for n in self._annotations()}


_pd = types.ModuleType("pydantic")
_pd.BaseModel = BaseModel
_pd.Field = Field
sys.modules["pydantic"] = _pd


# ===========================================================================
# Fake in-memory database session
# ===========================================================================
class FakeQuery:
    def __init__(self, rows, columns=None):
        self.rows = list(rows)
        self.columns = columns

    def filter(self, *conditions):
        rows = self.rows
        for cond in conditions:
            rows = [r for r in rows if cond(r)]
        return FakeQuery(rows, self.columns)

    def order_by(self, *specs):
        rows = list(self.rows)
        for spec in reversed(specs):
            if isinstance(spec, tuple):
                direction, field = spec
            else:
                direction, field = "asc", getattr(spec, "name", None)
            if not field:
                continue
            rows.sort(
                key=lambda r: (getattr(r, field, None) is None, getattr(r, field, None)),
                reverse=(direction == "desc"),
            )
        return FakeQuery(rows, self.columns)

    def limit(self, n):
        return FakeQuery(self.rows[:n], self.columns)

    def first(self):
        rows = self._materialise()
        return rows[0] if rows else None

    def all(self):
        return self._materialise()

    def count(self):
        return len(self.rows)

    def _materialise(self):
        if self.columns:
            return [tuple(getattr(r, c.name, None) for c in self.columns) for r in self.rows]
        return self.rows


class FakeDB:
    """Good enough for the auth router: holds User rows in a list."""

    def __init__(self):
        self.rows = []
        self._next_id = 1
        self.commits = 0

    def query(self, *entities):
        first = entities[0]
        if isinstance(first, Col):
            # Multi-column select, e.g. query(User.name, User.email, ...).
            # Keep rows whose class actually declares that column.
            def owns(row):
                return any(vars(k).get(first.name) is first for k in type(row).__mro__)

            return FakeQuery([r for r in self.rows if owns(r)], list(entities))
        return FakeQuery([r for r in self.rows if isinstance(r, first)])

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1
        self.rows.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass

    def flush(self):
        pass


def load_app():
    """Import the real application modules under the shim."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    from app import deps, models, schemas, security
    from app.routers import auth
    return models, schemas, security, deps, auth
