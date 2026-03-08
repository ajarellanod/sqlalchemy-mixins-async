from __future__ import annotations

from sqlalchemy.orm import Mapper, RelationshipProperty


class classproperty:
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


def get_relations(cls_or_mapper) -> list[RelationshipProperty]:
    mapper = cls_or_mapper if isinstance(cls_or_mapper, Mapper) else cls_or_mapper.__mapper__
    return [attr for attr in mapper.attrs if isinstance(attr, RelationshipProperty)]


def path_to_relations_list(cls_or_mapper, path: str) -> list[RelationshipProperty]:
    relations = get_relations(cls_or_mapper)
    relation_path: list[RelationshipProperty] = []
    for item in path.split("."):
        for relation in relations:
            if relation.key == item:
                relation_path.append(relation)
                relations = get_relations(relation.entity)
                break
    return relation_path
