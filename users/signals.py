"""Normal ORM/admin mutations invalidate existing projections, never auto-publish."""
from django.db.models.signals import post_save, post_delete, pre_save
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


@receiver(pre_save, sender=FilePost)
def invalidate_previous_case_on_move(sender, instance, using, **kwargs):
    if instance.pk:
        previous = FilePost.objects.using(using).filter(pk=instance.pk).values_list('post_id', flat=True).first()
        if previous and previous != instance.post_id:
            Case.objects.using(using).filter(pk=previous, projection_stale=False).update(projection_stale=True)
