"""Generic classification-metrics endpoint: accuracy, precision, recall, F1."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.metrics import ClassMetrics, MetricsRequest, MetricsResponse

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


def _per_class_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict[str, ClassMetrics]:
    per_class: dict[str, ClassMetrics] = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        support = sum(1 for t in y_true if t == label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[label] = ClassMetrics(precision=precision, recall=recall, f1=f1, support=support)
    return per_class


@router.post("/classification", response_model=MetricsResponse)
def classification_metrics(payload: MetricsRequest) -> MetricsResponse:
    """Score predicted labels against ground truth: accuracy, precision, recall, F1."""
    if len(payload.y_true) != len(payload.y_pred):
        raise HTTPException(status_code=422, detail="y_true and y_pred must be the same length.")

    y_true = [str(value) for value in payload.y_true]
    y_pred = [str(value) for value in payload.y_pred]
    labels = [str(value) for value in payload.labels] if payload.labels else sorted(set(y_true) | set(y_pred))

    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    per_class = _per_class_metrics(y_true, y_pred, labels)

    if payload.average == "binary":
        positive = str(payload.positive_label) if payload.positive_label is not None else labels[0]
        if positive not in per_class:
            raise HTTPException(status_code=422, detail=f"positive_label {positive!r} not found in labels.")
        chosen = per_class[positive]
        precision, recall, f1 = chosen.precision, chosen.recall, chosen.f1
    elif payload.average == "weighted":
        total = sum(metric.support for metric in per_class.values()) or 1
        precision = sum(metric.precision * metric.support for metric in per_class.values()) / total
        recall = sum(metric.recall * metric.support for metric in per_class.values()) / total
        f1 = sum(metric.f1 * metric.support for metric in per_class.values()) / total
    else:  # macro
        count = len(per_class) or 1
        precision = sum(metric.precision for metric in per_class.values()) / count
        recall = sum(metric.recall for metric in per_class.values()) / count
        f1 = sum(metric.f1 for metric in per_class.values()) / count

    return MetricsResponse(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        support=len(y_true),
        average=payload.average,
        per_class=per_class,
    )
