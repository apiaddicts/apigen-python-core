from pydantic import BaseModel
from typing import Optional
from datetime import datetime

{% for resource in cookiecutter.resources.resource_list %}
class {{ resource.model_name }}Base(BaseModel):
    {% for field in resource.fields %}
    {% if field.name != 'id' %}
    {{ field.name }}: {% if not field.required %}Optional[{{ field.type }}] = None{% else %}{{ field.type }}{% endif %}
    {% endif %}
    {% endfor %}

class {{ resource.model_name }}Create({{ resource.model_name }}Base):
    pass

class {{ resource.model_name }}({{ resource.model_name }}Base):
    id: str

    class Config:
        orm_mode = True

{% endfor %}
