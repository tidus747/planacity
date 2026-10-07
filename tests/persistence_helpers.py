"""Helpers for constructing authentic legacy persistence fixtures."""


def strip_work_context(data: dict) -> None:
    """Remove work fields added after schema 7 from current and baseline work."""
    fields = ("description", "labels", "primary_group_id", "priority")
    for item in data["plan"]["work_items"]:
        for field in fields:
            item.pop(field)
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            for field in fields:
                record["item"].pop(field)


def strip_work_priority(data: dict) -> None:
    """Remove the field introduced by schema 9 from current and baseline work."""
    for item in data["plan"]["work_items"]:
        item.pop("priority")
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            record["item"].pop("priority")
