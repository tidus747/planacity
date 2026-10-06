"""Helpers for constructing authentic legacy persistence fixtures."""


def strip_work_context(data: dict) -> None:
    """Remove fields introduced by schema 8 from current and baseline work."""
    fields = ("description", "labels", "primary_group_id")
    for item in data["plan"]["work_items"]:
        for field in fields:
            item.pop(field)
    for source in data["plan"].get("imports", ()):
        for record in source["records"]:
            for field in fields:
                record["item"].pop(field)
