from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_FILTER_KEYS = {"dateFrom", "dateTo", "status", "applicant"}
ALLOWED_QUERY_MODES = {"q", "qn"}


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50, alias="pageSize")
    query_mode: str = Field(default="qn", alias="queryMode")
    sort: str | None = None
    datasets: list[str] | None = None
    include_facets: int | None = Field(default=None, alias="includeFacets")
    filters: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        return value.strip()

    @field_validator("query_mode")
    @classmethod
    def validate_query_mode(cls, value: str) -> str:
        if value not in ALLOWED_QUERY_MODES:
            raise ValueError("queryMode must be either 'q' or 'qn'")
        return value

    @field_validator("include_facets")
    @classmethod
    def validate_include_facets(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in (0, 1):
            raise ValueError("includeFacets must be 0 or 1")
        return value

    @field_validator("filters")
    @classmethod
    def whitelist_filters(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        extra = set(value.keys()) - ALLOWED_FILTER_KEYS
        if extra:
            raise ValueError(f"Unsupported filters: {sorted(extra)}")
        return value


class PatentItem(BaseModel):
    id: str
    title: str
    published_at: str | None = Field(default=None, alias="publishedAt")
    applicant: str | None = None
    status: str | None = None
    snippet: str | None = None
    url: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class Pagination(BaseModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    has_next: bool = Field(alias="hasNext")

    model_config = ConfigDict(populate_by_name=True)


class MetaInfo(BaseModel):
    source: str = "rospatent"
    request_id: str = Field(alias="requestId")
    cached: bool = False

    model_config = ConfigDict(populate_by_name=True)


class SearchResponse(BaseModel):
    items: list[PatentItem]
    pagination: Pagination
    meta: MetaInfo
