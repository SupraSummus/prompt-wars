from django.db import models

from warriors.models import Warrior
from warriors.tasks import update_rating


while True:
    update_rating()
    print(Warrior.objects.all().aggregate(
        rating_sum=models.Sum('rating'),
        rating_error_sum=models.Sum('rating_error'),
    ))
