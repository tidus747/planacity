"""Helpers for constructing authentic legacy persistence fixtures."""


def strip_work_context(data: dict) -> None:
    """Remove work fields added after schema 7 from current and baseline work."""
    fields = ("description", "labels", "primary_group_id", "priority", "assignee_id")
    for item in data["plan"]["work_items"]:
        for field in fields:
            item.pop(field)
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            for field in fields:
                record["item"].pop(field)
            record.pop("external_priority", None)


def strip_work_priority(data: dict) -> None:
    """Remove the field introduced by schema 9 from current and baseline work."""
    for item in data["plan"]["work_items"]:
        item.pop("priority")
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            record["item"].pop("priority")


def strip_external_priority(data: dict) -> None:
    """Remove the imported source field introduced by schema 10."""
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            record.pop("external_priority", None)


def strip_work_assignee(data: dict) -> None:
    """Remove the canonical ownership field introduced by schema 11."""
    for item in data["plan"]["work_items"]:
        item.pop("assignee_id")
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            record["item"].pop("assignee_id")
