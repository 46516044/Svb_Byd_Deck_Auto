import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.hp_detection import load_mnist_model, predict_digit_mnist


def test_opencv_dnn_loads_mnist_model() -> None:
    model = load_mnist_model(str(PROJECT_ROOT / "models" / "mnist_adv.onnx"))
    prediction = predict_digit_mnist(model, np.zeros((28, 28), dtype=np.uint8))

    assert 0 <= prediction <= 9


def test_mnist_rejects_unexpected_input_shape() -> None:
    model = load_mnist_model(str(PROJECT_ROOT / "models" / "mnist_adv.onnx"))

    assert predict_digit_mnist(model, np.zeros((27, 28), dtype=np.uint8)) == -1


if __name__ == "__main__":
    test_opencv_dnn_loads_mnist_model()
    test_mnist_rejects_unexpected_input_shape()
    print("smoke_mnist_runtime: ok")
