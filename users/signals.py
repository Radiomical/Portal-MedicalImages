"""Normal ORM/admin mutations invalidate existing projections, never auto-publish."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from blog.models import Post
from .models import FilePost, Case


@receiver(post_save, sender=FilePost)
@receiver(post_delete, sender=FilePost)
def invalidate_file_projection(sender, instance, using, **kwargs):
    Case.objects.using(using).filter(pk=instance.post_id, projection_stale=False).update(projection_stale=True)


@receiver(post_save, sender=Post)
def invalidate_case_projection(sender, instance, using, **kwargs):
    Case.objects.using(using).filter(pk=instance.pk, projection_stale=False).update(projection_stale=True)
