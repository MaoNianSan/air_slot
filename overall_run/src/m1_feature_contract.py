from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .utils import stable_hash


class M1FeatureContractError(RuntimeError):
    pass


def _dtype_family(dtype: Any) -> str:
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if (
        pd.api.types.is_object_dtype(dtype)
        or pd.api.types.is_string_dtype(dtype)
        or isinstance(dtype, pd.CategoricalDtype)
    ):
        return "categorical"
    return str(dtype)


@dataclass(frozen=True)
class M1FeatureContract:
    feature_names: tuple[str, ...]
    feature_order: tuple[str, ...]
    dtypes: dict[str, str]
    categorical_columns: tuple[str, ...]
    null_policy: dict[str, str]
    contract_hash: str
    contract_version: str = "M1_PREVIOUS_LEG_V1"

    @classmethod
    def build(
        cls,
        frame: pd.DataFrame,
        feature_names: list[str],
        categorical_columns: list[str],
        *,
        contract_version: str = "M1_PREVIOUS_LEG_V1",
    ) -> "M1FeatureContract":
        names = tuple(str(column) for column in feature_names)
        categorical = tuple(str(column) for column in categorical_columns)
        if not names or len(names) != len(set(names)):
            raise M1FeatureContractError("M1_FEATURE_NAMES_INVALID")
        missing = [column for column in names if column not in frame.columns]
        if missing:
            raise M1FeatureContractError("M1_FEATURE_COLUMNS_MISSING:" + ",".join(missing))
        if any(column not in names for column in categorical):
            raise M1FeatureContractError("M1_CATEGORICAL_COLUMNS_OUTSIDE_FEATURES")
        dtypes = {column: _dtype_family(frame[column].dtype) for column in names}
        null_policy = {
            column: ("most_frequent" if column in categorical else "median")
            for column in names
        }
        payload = {
            "contract_version": str(contract_version),
            "feature_names": list(names),
            "feature_order": list(names),
            "dtypes": dtypes,
            "categorical_columns": list(categorical),
            "null_policy": null_policy,
        }
        return cls(
            feature_names=names,
            feature_order=names,
            dtypes=dtypes,
            categorical_columns=categorical,
            null_policy=null_policy,
            contract_hash=stable_hash(payload),
            contract_version=str(contract_version),
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "feature_names": list(self.feature_names),
            "feature_order": list(self.feature_order),
            "dtypes": self.dtypes,
            "categorical_columns": list(self.categorical_columns),
            "null_policy": self.null_policy,
        }

    def validate_integrity(self) -> None:
        if self.feature_names != self.feature_order:
            raise M1FeatureContractError("M1_FEATURE_ORDER_CONTRACT_MISMATCH")
        if set(self.dtypes) != set(self.feature_names):
            raise M1FeatureContractError("M1_DTYPE_CONTRACT_MISMATCH")
        if set(self.null_policy) != set(self.feature_names):
            raise M1FeatureContractError("M1_NULL_POLICY_CONTRACT_MISMATCH")
        if stable_hash(self._payload()) != self.contract_hash:
            raise M1FeatureContractError("M1_FEATURE_CONTRACT_HASH_MISMATCH")

    def validate_artifact_columns(
        self,
        feature_columns: list[str],
        categorical_columns: list[str],
    ) -> None:
        self.validate_integrity()
        if tuple(feature_columns) != self.feature_names:
            raise M1FeatureContractError("M1_ARTIFACT_FEATURE_ORDER_MISMATCH")
        if tuple(categorical_columns) != self.categorical_columns:
            raise M1FeatureContractError("M1_ARTIFACT_CATEGORICAL_ORDER_MISMATCH")

    def validate_feature_frame(self, frame: pd.DataFrame) -> None:
        self.validate_integrity()
        actual = tuple(str(column) for column in frame.columns)
        if actual != self.feature_order:
            raise M1FeatureContractError(
                "M1_INFERENCE_FEATURE_ORDER_MISMATCH:"
                f"expected={list(self.feature_order)}:actual={list(actual)}"
            )
        for column in self.feature_names:
            actual_family = _dtype_family(frame[column].dtype)
            if actual_family != self.dtypes[column]:
                raise M1FeatureContractError(
                    "M1_INFERENCE_DTYPE_MISMATCH:"
                    f"{column}:expected={self.dtypes[column]}:actual={actual_family}"
                )

    def select_authoritative(self, frame: pd.DataFrame) -> pd.DataFrame:
        missing = [column for column in self.feature_names if column not in frame.columns]
        if missing:
            raise M1FeatureContractError("M1_INFERENCE_FEATURES_MISSING:" + ",".join(missing))
        selected = frame.loc[:, list(self.feature_order)]
        self.validate_feature_frame(selected)
        return selected

    def to_dict(self) -> dict[str, Any]:
        self.validate_integrity()
        return {**self._payload(), "contract_hash": self.contract_hash}
