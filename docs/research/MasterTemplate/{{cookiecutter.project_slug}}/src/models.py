from sqlalchemy import Column, Integer, String, Boolean, DateTime
from .database import Base

{% for resource in cookiecutter.resources.resource_list %}
class {{ resource.model_name }}(Base):
    __tablename__ = "{{ resource.slug }}"

    {% for field in resource.fields %}
    {{ field.name }} = Column({{ field.sa_type }}{% if field.name == 'id' %}, primary_key=True, index=True{% endif %})
    {% endfor %}

{% endfor %}
