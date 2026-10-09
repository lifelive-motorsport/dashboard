// Journal des nouveautés affiché sur la page d'accueil (les plus récentes en premier). À compléter à chaque ajout important de section ou de fonctionnalité.
const CHANGELOG = [
  {date: 'Octobre 2026', title: 'Nouveau menu en 4 chapitres', tag: 'Application', items: [
    'Piloter (Tableaux de bord), Planifier (Événements, Ressources), Consigner (Pointages, Roulages, Consommables), Administrer (Équipage, Connexions).',
    'Les modules à venir sont déjà visibles (« bientôt ») et leurs droits d’accès peuvent déjà être donnés par catégorie.']},
  {date: 'Octobre 2026', title: 'Filtre BU sur Vue d’ensemble et l’accueil', tag: 'Vue d’ensemble', items: [
    'Filtre à deux niveaux (Toutes / XC Cross / CARS, puis Modern Rally, Historic Racing, Historic Rally) sur l’accueil et sur les pages Vue d’ensemble ; le logo prend la couleur de la BU choisie.',
    'Créances et dettes par BU, avec rapprochement exact du total de la société ; jauges qui montrent aussi les marges négatives ; effectifs (ETP) par BU sur l’accueil.']},
  {date: 'Octobre 2026', title: 'Logbook : page d’accueil, nouvelle identité et nouveau menu', tag: 'Application', items: [
    'Nouvelle page d’accueil personnalisée, avec vos indicateurs clés selon vos accès.',
    'L’application devient « Logbook », avec sa charte graphique (couleurs, polices, logo), et le menu regroupe les anciens tableaux de bord sous « Tableaux de bord ».']},
  {date: 'Octobre 2026', title: 'Utilisateurs, catégories et droits d’accès', tag: 'Settings', items: [
    'Settings › Utilisateurs : le Super User crée les utilisateurs et choisit leur rôle (Standard, Administrateur ou catégorie).',
    'Catégories sur mesure : on nomme une catégorie et on coche les sections et sous-sections accessibles ; le serveur n’ouvre rien d’autre.']},
  {date: 'Octobre 2026', title: 'Projections annualisées', tag: 'Vue d’ensemble', items: [
    'Chiffre d’affaires : CA réalisé par mois (XC, CARS), CA espéré à encoder pour les mois à venir, comparaison avec l’année précédente.',
    'Marge brute et marge nette projetées à partir du CA espéré.']},
  {date: 'Octobre 2026', title: 'Contrôle des marges sur produits et sur devis TN11', tag: 'Détail XC', items: [
    'Contrôle des marges s/ produits : prix de vente, coût Odoo et coût réel estimé (achats et transport) des articles à code PIF.',
    'Contrôle des marges s/ TN11 : on dépose un devis PDF ; chaque ligne vendue est comparée à Odoo, avec le détail des nomenclatures et la main-d’œuvre.']},
  {date: 'Octobre 2026', title: 'Marge nette', tag: 'Vue d’ensemble', items: [
    'Nouvel onglet Marge nette (Vue d’ensemble, XC, CARS) avec personnel, véhicules, frais généraux, Shared Services, Management et marketing.',
    'Hypothèses d’imputation visibles et modifiables, avec simulation pour les utilisateurs qui ne sont pas propriétaires des valeurs de référence.']},
  {date: 'Septembre 2026', title: 'Service Vehicles, frais généraux et personnel', tag: 'Gestion', items: [
    'Imputation des frais de véhicules aux BU (carburant, agendas, rapprochement avec la comptabilité).',
    'Frais généraux et coûts de personnel par BU, avec fiches de paie.']},
];
