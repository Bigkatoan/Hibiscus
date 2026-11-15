"""What a bundle needs on top of LeLab's LeRobot install (QC-ml-1).

The documented target environment is the LeLab venv (``~/lelab/leLab/.venv``): the same LeRobot
0.7.1 commit the worker pins, but installed WITHOUT the optional extras. Measured read-only on the
reference box (2026-11-15): ``lerobot 0.7.1``, ``torch 2.15.0+cu132``, and none of
``diffusers``, ``transformers``, ``peft``, ``tokenizers``, ``sentencepiece``, ``num2words``,
``scipy``. So an ACT / VQ-BeT bundle loads there, while Diffusion fails with
``ImportError: 'diffusers' is required but not installed`` and SmolVLA / pi0 / pi05 need
``transformers``.

The worker image has every extra, so a load check in the worker interpreter proves nothing about
LeLab. ``export.load_check`` therefore runs the LeLab check either with a real LeLab interpreter
(``HIBISCUS_EXPORT_LOAD_CHECK_PYTHON``) or, by default, in the worker interpreter with the modules
of :data:`LELAB_MISSING_MODULES` hidden from the import system (same LeRobot commit, same
loading code path, same missing packages).
"""

from __future__ import annotations

import shlex

#: Top-level modules that LeRobot's optional extras install and LeLab's venv does not have.
LELAB_MISSING_MODULES: tuple[str, ...] = (
    "diffusers",
    "transformers",
    "peft",
    "tokenizers",
    "sentencepiece",
    "num2words",
    "scipy",
)

#: LeRobot extras a policy type needs at load time (lerobot 0.7.1 pyproject).
POLICY_EXTRAS: dict[str, tuple[str, ...]] = {
    "diffusion": ("diffusion",),
    "smolvla": ("smolvla",),
    "pi0": ("pi",),
    "pi05": ("pi",),
}

#: pip requirements of those extras, exactly as lerobot 0.7.1's metadata pins them. LeRobot 0.7.1
#: is not on PyPI under that version, so ``pip install 'lerobot[diffusion]==0.7.1'`` would fail:
#: the card tells users to install the packages themselves.
EXTRA_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "diffusion": ("diffusers>=0.38.0,<0.40.0",),
    "smolvla": ("transformers>=5.22.0,<5.23.0", "num2words>=0.5.14,<0.6.0"),
    "pi": ("transformers>=5.22.0,<5.23.0", "scipy>=1.14.0,<2.0.0", "sentencepiece>=0.2.0,<0.3.0"),
    "peft": ("transformers>=5.22.0,<5.23.0", "peft>=0.18.0,<1.0.0"),
}

#: Importable module of each requirement (for the run_on_robot.sh pre-check).
_MODULE_OF = {
    "diffusers": "diffusers",
    "transformers": "transformers",
    "num2words": "num2words",
    "scipy": "scipy",
    "sentencepiece": "sentencepiece",
    "peft": "peft",
}


def required_extras(policy_type: str, *, peft: bool = False) -> list[str]:
    extras = list(POLICY_EXTRAS.get(policy_type, ()))
    if peft and "peft" not in extras:
        extras.append("peft")
    return extras


def extra_requirements(policy_type: str, *, peft: bool = False) -> list[str]:
    """pip requirement strings this bundle needs inside the LeLab venv (empty = none)."""
    out: list[str] = []
    for extra in required_extras(policy_type, peft=peft):
        for req in EXTRA_REQUIREMENTS[extra]:
            if req not in out:
                out.append(req)
    return out


def required_modules(requirements: list[str]) -> list[str]:
    mods: list[str] = []
    for req in requirements:
        name = req.split(">", 1)[0].split("<", 1)[0].split("=", 1)[0].strip()
        mod = _MODULE_OF.get(name, name)
        if mod not in mods:
            mods.append(mod)
    return mods


def pip_command(requirements: list[str]) -> str:
    return "pip install " + " ".join(shlex.quote(r) for r in requirements)
