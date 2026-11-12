IMAGE STYLIZER 1.0 — KIT DE COMPILATION WINDOWS
================================================

CE QUE CONTIENT CE ZIP
----------------------
- Le code complet de la V8.4 stabilisee, avec le logo applique a la fenetre.
- assets/image_stylizer.ico : icone Windows (16 a 256 px).
- CONSTRUIRE_WINDOWS.bat : recommande, exe portable dans un dossier.
- CONSTRUIRE_EXE_UNIQUE.bat : alternative, un seul exe.
- requirements_build.txt : dependances utilisees par le build.
- Les tests automatiques et un utilitaire benchmark, facultatifs.

PREPARATION
-----------
1. Extraire TOUT le ZIP dans un nouveau dossier de ton choix.
2. Sous Windows, avoir Python installe (3.12 recommande) avec pip.
3. Avoir une connexion Internet pour la premiere compilation : les
   dependances seront telechargees dans .venv_build, independamment
   de ton environnement VS Code habituel.

COMPILER — VERSION RECOMMANDEE
-----------------------------
Double-cliquer sur CONSTRUIRE_WINDOWS.bat.
Le script cree un environnement virtuel, installe les bibliotheques,
puis construit l'executable.

Resultat : dist\Image Stylizer\Image Stylizer.exe
Pour deplacer ou partager le logiciel, copier le dossier ENTIER
"dist\Image Stylizer" (l'exe et le sous-dossier _internal).

COMPILER — EXE UNIQUE (ALTERNATIVE)
----------------------------------
Double-cliquer sur CONSTRUIRE_EXE_UNIQUE.bat.
Resultat : dist_unique\Image Stylizer.exe
Le demarrage sera souvent plus lent et certains antivirus peuvent
se montrer plus mefiants envers ce format. Ce n'est pas un installeur.

OU SONT LES PRESETS ET PREFERENCES ?
-----------------------------------
Les presets existants ne sont PAS embarques dans l'exe, mais restent
sur ton PC dans C:\Users\<toi>\.image_stylizer\presets.json.
Ce choix evite de les ecraser a chaque nouvelle compilation.
Les preferences (chemins et options d'export) restent stockees dans
QSettings, avec migration depuis l'ancienne version.

TEST RAPIDE
-----------
Lancer l'exe depuis son dossier de sortie, puis verifier :
  1. L'icone apparait dans la fenetre et la barre des taches.
  2. Les presets existants sont visibles.
  3. Importer une image, previsualiser puis exporter un PNG.
  4. Fermer et relancer : chemins et options restent conserves.

EN CAS D'ERREUR
---------------
- Relancer le .bat dans le terminal Windows pour lire les messages.
- Si l'exe ne demarre pas, lancer "python main.py" dans le projet
  ou compiler temporairement avec l'option --console au lieu de
  --windowed pour faire apparaitre la trace d'erreur.
- Un .exe non signe peut declencher un avertissement SmartScreen lors
  d'un telechargement ou partage. Cela ne signifie pas automatiquement
  qu'il est malveillant ; ne pas contourner aveuglement un avertissement.
- Ne pas essayer de compiler ce projet Windows sous Linux : PyInstaller
  ne produit pas d'executable Windows en cross-compilation ordinaire.

NOTES
-----
Pas de nouveaux effets ni de changements au rendu des images : seul
main.py a ete adapte pour integrer l'icone de la fenetre.
Le code de base provient de ta V8.4 stabilisee et validee.
