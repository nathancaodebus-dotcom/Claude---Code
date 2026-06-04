from django.db import models


class Produit(models.Model):
    nom = models.CharField(max_length=200)
    description = models.TextField()
    prix = models.DecimalField(max_digits=8, decimal_places=2)
    prix_barre = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Produit'
        verbose_name_plural = 'Produits'

    def __str__(self):
        return self.nom

    @property
    def reduction_pct(self):
        if self.prix_barre and self.prix_barre > 0:
            return int((1 - self.prix / self.prix_barre) * 100)
        return 0


class Avis(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='avis')
    prenom = models.CharField(max_length=100)
    ville = models.CharField(max_length=100)
    note = models.PositiveSmallIntegerField(default=5)
    texte = models.TextField()
    verifie = models.BooleanField(default=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Avis client'
        verbose_name_plural = 'Avis clients'
        ordering = ['-date']

    def __str__(self):
        return f"{self.prenom} — {self.note}★"

    @property
    def etoiles(self):
        return range(self.note)


class Commande(models.Model):
    STATUTS = [
        ('en_attente', 'En attente'),
        ('payee', 'Payée'),
        ('expediee', 'Expédiée'),
        ('livree', 'Livrée'),
        ('annulee', 'Annulée'),
    ]
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True)
    quantite = models.PositiveIntegerField(default=1)
    nom_client = models.CharField(max_length=200)
    email = models.EmailField()
    adresse = models.TextField()
    montant_total = models.DecimalField(max_digits=8, decimal_places=2)
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_attente')
    date_commande = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Commande'
        verbose_name_plural = 'Commandes'
        ordering = ['-date_commande']

    def __str__(self):
        return f"Commande #{self.pk} — {self.nom_client}"
