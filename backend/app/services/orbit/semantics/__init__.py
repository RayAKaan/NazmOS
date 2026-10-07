"""Universal semantic vocabulary, column mapping and row classification.

One authority for what a column means and what a row is. See
:mod:`app.services.orbit.semantics.vocabulary` for the rules these follow.
"""

from app.services.orbit.semantics.column_mapper import (
    AMBIGUITY_MARGIN,
    MIN_MAPPING_CONFIDENCE,
    ArtifactColumnMap,
    ColumnCandidate,
    ColumnMapping,
    ColumnMappingStatus,
    ColumnProfile,
    GENERIC_MONEY_CANDIDATES,
    GENERIC_MONEY_HEADERS,
    map_column,
    map_columns,
    parse_numeric,
    profile_column,
)
from app.services.orbit.semantics.row_roles import (
    RowClassification,
    RowRoleReport,
    classify_row,
    classify_rows,
)
from app.services.orbit.semantics.vocabulary import (
    ALL_ROLES,
    GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND,
    GENERIC_QUANTITY_ROLE_BY_ARTIFACT_KIND,
    PRIMARY_DOMAIN_BY_ARTIFACT_KIND,
    ROLES_BY_ARTIFACT_KIND,
    designated_role_for,
    ALIAS_INDEX,
    CURRENCY_ROLES,
    DATE_ROLES,
    ENTITY_ROLES,
    TRANSACTIONAL_ROLES,
    CurrencyBehaviour,
    SemanticRole,
    UnitDimension,
    ValueType,
    domain_of,
    exact_alias_lookup,
    get_role,
    is_currency_role,
    roles_for_domain,
    unit_dimension_of,
    validate_vocabulary,
)

__all__ = [
    "ALL_ROLES", "ALIAS_INDEX", "CURRENCY_ROLES", "DATE_ROLES", "ENTITY_ROLES",
    "TRANSACTIONAL_ROLES", "AMBIGUITY_MARGIN", "MIN_MAPPING_CONFIDENCE",
    "ArtifactColumnMap", "ColumnCandidate", "ColumnMapping", "ColumnMappingStatus",
    "ColumnProfile", "CurrencyBehaviour", "RowClassification", "RowRoleReport",
    "SemanticRole", "UnitDimension", "ValueType", "GENERIC_MONEY_CANDIDATES",
    "GENERIC_MONEY_HEADERS", "GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND",
    "GENERIC_QUANTITY_ROLE_BY_ARTIFACT_KIND", "PRIMARY_DOMAIN_BY_ARTIFACT_KIND",
    "ROLES_BY_ARTIFACT_KIND", "classify_row", "classify_rows", "designated_role_for",
    "domain_of", "exact_alias_lookup", "get_role", "is_currency_role", "map_column",
    "map_columns", "parse_numeric", "profile_column", "roles_for_domain",
    "unit_dimension_of", "validate_vocabulary",
]