# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-10-25 16:15
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pinax_stripe', '0019_merge_20171025_1519'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='stripe_publishable_key',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
