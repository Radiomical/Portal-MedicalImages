from django import template

register = template.Library()

@register.filter
def distribute_fields(form):
    classes = ['first', 'second', 'third']
    fields = list(form)
    num_fields = len(fields)
    num_classes = len(classes)
    fields_per_class = num_fields // num_classes
    extra_fields = num_fields % num_classes
    field_index = 0
    result = []
    for i in range(num_classes):
        num_extra_fields = 1 if i < extra_fields else 0
        start_index = field_index
        end_index = start_index + fields_per_class + num_extra_fields
        result.append((fields[start_index:end_index], classes[i]))
        field_index = end_index
    return result