"""Kronos financial foundation model, vendored for ZERO.

Vendored from the open-source Kronos project
(https://github.com/shiyu-coder/Kronos), MIT License.

Only import paths were changed relative to upstream: the absolute
``from model.module import *`` (and its ``sys.path`` hack) in kronos.py was
replaced with the relative ``from .module import *``. The code is otherwise
functionally identical to upstream ``model/``.

Public exports: ``Kronos``, ``KronosTokenizer``, ``KronosPredictor``
(plus the upstream ``model_dict`` / ``get_model_class`` helpers).
"""
from .kronos import KronosTokenizer, Kronos, KronosPredictor

model_dict = {
    'kronos_tokenizer': KronosTokenizer,
    'kronos': Kronos,
    'kronos_predictor': KronosPredictor
}


def get_model_class(model_name):
    if model_name in model_dict:
        return model_dict[model_name]
    else:
        print(f"Model {model_name} not found in model_dict")
        raise NotImplementedError
