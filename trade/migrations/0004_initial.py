# Generated by Django 5.1.6 on 2025-04-04 14:53

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('trade', '0003_delete_orderhistory'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpotTrade',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('pair', models.CharField(max_length=10)),
                ('open_position', models.DecimalField(decimal_places=2, max_digits=10)),
                ('sold_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('sold_or_not', models.BooleanField(default=False)),
                ('profit', models.DecimalField(decimal_places=2, max_digits=10)),
                ('fee', models.DecimalField(decimal_places=2, max_digits=10)),
                ('exceed_or_not', models.BooleanField(default=False)),
                ('target_after_exceed', models.DecimalField(decimal_places=2, max_digits=10)),
            ],
        ),
        migrations.CreateModel(
            name='Trade',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('pair', models.CharField(max_length=10)),
                ('method', models.CharField(choices=[('buy', 'buy'), ('sell', 'sell')], max_length=10)),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('fee', models.DecimalField(decimal_places=2, max_digits=10)),
                ('trade_date', models.DateTimeField(auto_now_add=True)),
                ('trade_or_not', models.BooleanField(default=False)),
            ],
        ),
    ]
