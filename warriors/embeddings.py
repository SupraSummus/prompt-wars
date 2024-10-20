import voyageai
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django_goals.models import AllDone, Goal, RetryMeLater, schedule


class EmbeddingMixin(models.Model):
    class Meta:
        abstract = True

    voyage_3_embedding = ArrayField(
        models.FloatField(),
        size=1024,
        default=list,
    )
    voyage_3_embedding_goal = models.OneToOneField(
        to=Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def schedule_voyage_3_embedding(self):
        if (
            self.voyage_3_embedding or
            self.voyage_3_embedding_goal
        ):
            return
        self.voyage_3_embedding_goal = schedule(ensure_voyage_3_embedding)
        self.save(update_fields=('voyage_3_embedding_goal',))


def ensure_voyage_3_embedding(goal):
    text_unit = goal.textunit
    if text_unit.voyage_3_embedding:
        return AllDone()
    try:
        text_unit.voyage_3_embedding = get_embedding(text_unit.content)
    except voyageai.error.RateLimitError:
        return RetryMeLater(
            message='Voyage AI rate limit exceeded',
            precondition_date=timezone.now() + timezone.timedelta(minutes=1),
        )
    text_unit.save(update_fields=('voyage_3_embedding',))
    return AllDone()


def get_embedding(content):
    response = voyage_client.embed([content], model='voyage-3')
    return response.embeddings[0]


voyage_client = voyageai.Client(
    api_key=settings.VOYAGE_API_KEY,
)
