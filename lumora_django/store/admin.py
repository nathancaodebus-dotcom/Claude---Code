from django.contrib import admin
from .models import Produit, Avis, Commande


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prix', 'prix_barre', 'stock', 'actif', 'date_creation')
    list_editable = ('prix', 'stock', 'actif')
    list_filter = ('actif',)
    search_fields = ('nom', 'description')


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display = ('prenom', 'ville', 'note', 'verifie', 'date')
    list_editable = ('verifie',)
    list_filter = ('note', 'verifie')
    search_fields = ('prenom', 'ville', 'texte')


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom_client', 'email', 'produit', 'quantite', 'montant_total', 'statut', 'date_commande')
    list_editable = ('statut',)
    list_filter = ('statut', 'date_commande')
    search_fields = ('nom_client', 'email')
    readonly_fields = ('date_commande',)
