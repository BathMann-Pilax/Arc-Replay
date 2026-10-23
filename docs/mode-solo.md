# Mode solo

Une tablette (iPad, Android) ou un PC portable seul, sans serveur ni Wi-Fi : l'appareil filme l'archer avec sa propre caméra et lui montre son geste avec quelques secondes de retard. C'est le mode dégradé pour les déplacements, les concours et l'extérieur.

**Adresse :** https://bathmann-pilax.github.io/Arc-Replay/

## Installer

1. Ouvrir l'adresse ci-dessus une première fois **avec internet**.
2. L'installer comme une application :
   - **iPad** (Safari) : bouton Partager → « Sur l'écran d'accueil » ;
   - **Android** (Chrome) : menu ⋮ → « Installer l'application » ;
   - **PC** (Chrome, Edge) : icône d'installation dans la barre d'adresse.
3. Ensuite, l'application s'ouvre et fonctionne **hors ligne**.

Au premier démarrage, autoriser l'accès à la caméra et au micro.

## Utiliser

1. Choisir la caméra : **Avant** (côté écran) ou **Arrière**, puis la qualité, puis « Démarrer ».
2. Poser l'appareil du côté vers lequel l'archer est tourné, hors de la trajectoire des flèches. Avec la caméra avant, l'appareil filme l'archer pendant qu'il regarde l'écran.
3. Tirer : l'image arrive avec le retard choisi (10 s par défaut, de 3 à 30 s dans « Réglages »).

| Bouton | Rôle |
|---|---|
| **Marquer un tir** | Sans micro : le tir est daté une seconde avant l'appui. |
| **Rejouer** | Dernière flèche en boucle (6 s avant le lâcher, 3 s après), à ×1, ×0,5 ou ×0,25. |
| **F1, F2…** | Rejouer une flèche de la volée en cours. |
| **Comparer** | Toucher deux flèches : côte à côte, ou « Superposer » (la seconde en transparence). |
| **Enregistrer la vidéo** | Pendant un rejeu : fabrique un fichier vidéo du clip. iPad et Android proposent « Enregistrer dans Fichiers / Photos » (ou une clé USB-C branchée) ; un PC le télécharge. |
| **Réglages** | Retard, image en miroir, nouvelle volée, annuler la dernière flèche, micro, caméra, qualité. |

**Micro** : le claquement de corde déclenche le tir. Dans « Réglages », regardez le niveau actuel sans tirer, puis placez le seuil juste au-dessus. Le point en haut à gauche passe au vert quand le seuil est dépassé. Plusieurs archers côte à côte : préférez « Marquer un tir ».

**Volées** : comme sur le serveur, une nouvelle volée commence après 6 flèches ou 90 s sans tir. Les vidéos de la volée précédente sont alors oubliées : seule la volée en cours reste en mémoire. Pour garder un clip, « Enregistrer la vidéo » avant la volée suivante.

## Qualité et appareil

| Qualité | Usage |
|---|---|
| Économe (640 px) | Tablettes anciennes ou d'entrée de gamme, longues séances sur batterie. |
| Standard (960 px) | Par défaut. |
| Haute (1280 px) | Appareil récent, pour voir les détails (doigts, décoché). |

« Réglages » affiche les images par seconde et la mémoire utilisée. Si les images par seconde tombent sous 20, baissez la qualité. Compter environ 50 à 150 Mo de mémoire selon la qualité et le retard.

L'écran reste allumé pendant la séance. Branchez l'appareil sur secteur ou batterie externe pour une longue séance.

## Limites

- **Une seule vue** : celle de l'appareil.
- **Pas de score ni de cible** : le mode solo ne fait que la vidéo.
- **Rien n'est gardé** à la fermeture de l'application, sauf les vidéos enregistrées.
- **https obligatoire** : les navigateurs n'ouvrent la caméra que sur une page sécurisée. L'adresse `http://10.42.0.1/solo` du serveur ne peut donc pas filmer ; utilisez l'adresse GitHub Pages, ou lancez la page en local sur un PC (voir ci-dessous).

## Lancer en local sur un PC

Sans internet du tout, sur un PC qui a le code :

```bash
cd frontend
npm ci
VITE_SOLO=1 npx vite build --outDir dist-solo
npx vite preview --outDir dist-solo --port 4173
```

Puis ouvrir `http://localhost:4173/` (`localhost` compte comme une page sécurisée).

## Comment ça marche

Tout tourne dans le navigateur. La caméra est lue par `getUserMedia` ; environ 30 fois par seconde, l'image est réduite et compressée en JPEG, puis gardée en mémoire avec son heure. L'affichage montre l'image prise il y a « retard » secondes ; un clip n'est qu'une liste de ces images, ce qui rend le ralenti et la comparaison immédiats. Cette méthode marche de la même façon sur Safari, Chrome et Edge, sans dépendre des formats vidéo de chaque navigateur. Le micro est analysé par la Web Audio API (crête par blocs de 20 ms, comme le détecteur du serveur). L'export recompose le clip dans une vidéo (MP4 sur Safari, MP4 ou WebM ailleurs) avec MediaRecorder.

Code : `frontend/src/solo/`. Publication : `.github/workflows/solo.yml`, à chaque modification de `frontend/` sur `main`.
