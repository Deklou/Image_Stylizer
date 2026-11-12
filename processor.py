"""Pipeline de traitement et export pleine résolution.

Les presets créés avant la V6 ne contiennent ni interrupteurs ni seed :
on active alors tous les effets et on adopte la seed par défaut.
"""

from pathlib import Path
import errno
import os
import tempfile

import numpy as np
from PIL import Image

from effects import (
    add_noise, apply_vignette, adjust_contrast, bloom,
    color_grade, gaussian_blur, posterize_np,
)


DEFAULT_NOISE_SEED = 12345


def process_image(image, parameters):
    # Les effets ne modifient jamais le tableau d'entrée en place.
    # Éviter la copie RGB systématique réduit le pic mémoire en HD/4K.
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    img_np = np.asarray(rgb)

    if parameters.get("blur_enabled", True) and int(parameters["blur_kernel"]) > 1:
        img_np = gaussian_blur(img_np, parameters["blur_kernel"])

    if parameters.get("bloom_enabled", True) and parameters["bloom_intensity"] > 0:
        img_np = bloom(
            img_np,
            parameters["bloom_threshold"],
            parameters["bloom_intensity"],
        )

    if parameters.get("posterize_enabled", True):
        img_np = posterize_np(img_np, parameters["poster_levels"])

    if parameters.get("noise_enabled", True) and parameters["noise_amount"] > 0:
        img_np = add_noise(
            img_np,
            parameters["noise_amount"],
            seed=parameters.get("noise_seed", DEFAULT_NOISE_SEED),
        )

    if parameters.get("grade_enabled", True) and (
        parameters["blue_strength"] != 1.0 or parameters["yellow_strength"] != 1.0
    ):
        img_np = color_grade(
            img_np,
            parameters["blue_strength"],
            parameters["yellow_strength"],
        )

    # Ces nouveaux effets sont facultatifs. Les anciens presets
    # (sans ces clés) continuent donc à produire exactement le même rendu.
    if parameters.get("contrast_enabled", False):
        img_np = adjust_contrast(img_np, parameters.get("contrast_factor", 1.0))
    if parameters.get("vignette_enabled", False):
        img_np = apply_vignette(img_np, parameters.get("vignette_amount", 30))

    return Image.fromarray(img_np)


def build_suffix(parameters):
    base = (
        f"BL{parameters['blur_kernel']}"
        f"_BT{parameters['bloom_threshold']}"
        f"_BI{round(parameters['bloom_intensity'] * 100)}"
        f"_PL{parameters['poster_levels']}"
        f"_N{parameters['noise_amount']}"
        f"_B{round(parameters['blue_strength'] * 100)}"
        f"_Y{round(parameters['yellow_strength'] * 100)}"
    )

    effect_keys = (
        "blur_enabled",
        "bloom_enabled",
        "posterize_enabled",
        "noise_enabled",
        "grade_enabled",
    )
    effects_mask = "".join("1" if parameters.get(key, True) else "0" for key in effect_keys)
    seed = int(parameters.get("noise_seed", DEFAULT_NOISE_SEED))
    suffix = f"{base}_S{seed}_E{effects_mask}"
    # Les suffixes de la V7 restent identiques quand ces effets sont éteints.
    c_on = bool(parameters.get("contrast_enabled", False))
    v_on = bool(parameters.get("vignette_enabled", False))
    if c_on or v_on:
        suffix += (
            f"_X{int(c_on)}{int(v_on)}"
            f"_C{round(float(parameters.get('contrast_factor', 1.0)) * 100)}"
            f"_V{round(float(parameters.get('vignette_amount', 30)))}"
        )
    return suffix


def export_image(input_path, output_dir, parameters, image_format="PNG", quality=90):
    """Traite puis publie l'export sans écraser ni laisser de fichier incomplet.

    L'encodage se fait d'abord dans un fichier temporaire placé dans le dossier
    cible. Une fois réussi, on publie un fichier complet sous un nom libre,
    sans écraser un précédent export.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    format_extensions = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
    image_format = str(image_format).upper()
    if image_format not in format_extensions:
        raise ValueError(f"Format d'export non pris en charge : {image_format}")
    if not (1 <= int(quality) <= 100):
        raise ValueError("La qualité doit être comprise entre 1 et 100.")

    suffix = build_suffix(parameters)
    extension = format_extensions[image_format]

    save_options = {}
    if image_format in ("JPEG", "WEBP"):
        save_options["quality"] = int(quality)
    if image_format == "JPEG":
        save_options["subsampling"] = 0

    temp_path = None
    try:
        # Le suffixe du temporaire conserve le format pour faciliter le debug.
        with tempfile.NamedTemporaryFile(
            prefix=".image_stylizer_", suffix=extension,
            dir=output_dir, delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        with Image.open(input_path) as image:
            result = process_image(image, parameters)
        result.save(temp_path, format=image_format, **save_options)
        result.close()

        # Publication atomique sans écrasement : un lien dur pointe vers le
        # fichier entièrement encodé. Les deux noms sont dans le même dossier.
        # Sur Windows, os.rename() est également atomique et refuse d'écraser
        # une destination déjà existante ; on l'utilise en solution de repli.
        counter = 1
        while True:
            extra = "" if counter == 1 else f"_{counter}"
            candidate = output_dir / f"{input_path.stem}_{suffix}{extra}{extension}"
            try:
                os.link(temp_path, candidate)
            except FileExistsError:
                counter += 1
                continue
            except OSError as exc:
                if os.name == "nt" and exc.errno in (
                    errno.EPERM, errno.EACCES, errno.ENOTSUP,
                    errno.EOPNOTSUPP, errno.EXDEV,
                ):
                    # os.rename() sur Windows échoue si candidate existe.
                    try:
                        os.rename(temp_path, candidate)
                    except FileExistsError:
                        counter += 1
                        continue
                    else:
                        temp_path = None
                        return candidate
                raise
            else:
                return candidate
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
