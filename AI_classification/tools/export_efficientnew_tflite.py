#!/usr/bin/env python3
import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import tf_keras as keras


DEFAULT_HUB_URL = "https://tfhub.dev/tensorflow/efficientnet/lite0/feature-vector/2"
DEFAULT_INPUT_SIZE = 224

# Preprocessing attuale del tuo progetto
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def build_model(
    hub_url: str,
    input_size: int = DEFAULT_INPUT_SIZE,
    l2_normalize: bool = True,
):
    """
    Modello finale:
      input: float32 [1, 224, 224, 3]
      expected external values: pixel raw 0..255
      internal preprocessing:
          x = (x / 255.0 - MEAN) / STD
      output:
          embedding float32 L2-normalizzato
    """
    inputs = keras.Input(
        shape=(input_size, input_size, 3),
        dtype=tf.float32,
        name="image",
    )

    # 0..255 -> 0..1
    x = keras.layers.Rescaling(1.0 / 255.0, name="rescale_255_to_01")(inputs)

    # ImageNet mean/std normalization
    mean = tf.constant(MEAN.reshape((1, 1, 1, 3)), dtype=tf.float32)
    std = tf.constant(STD.reshape((1, 1, 1, 3)), dtype=tf.float32)

    x = keras.layers.Lambda(
        lambda t: (t - mean) / std,
        name="imagenet_mean_std_norm",
    )(x)

    # TF Hub EfficientNet-Lite0 feature vector
    backbone = hub.KerasLayer(
        hub_url,
        trainable=False,
        output_key="default",
        name="efficientnet_lite0_feature_vector",
    )

    x = backbone(x)

    if l2_normalize:
        x = keras.layers.Lambda(
            lambda t: tf.math.l2_normalize(t, axis=-1),
            name="l2_normalize",
        )(x)

    model = keras.Model(
        inputs=inputs,
        outputs=x,
        name="efficientnet_lite0_embedding_imagenet_norm",
    )
    return model


def convert_to_tflite(
    model,
    output_path: Path,
    quantization: str = "float32",
):
    """
    quantization:
      - float32
      - float16
      - dynamic
    """
    converter = tf.lite.TFLiteConverter.from_keras_model(model)

    if quantization == "float32":
        pass
    elif quantization == "float16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
    elif quantization == "dynamic":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
    else:
        raise ValueError("quantization must be one of: float32, float16, dynamic")

    tflite_model = converter.convert()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(tflite_model)
    return output_path


def inspect_tflite_model(tflite_path: Path):
    interpreter = tf.lite.Interpreter(model_path=str(tflite_path))
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    print("\n=== TFLite inspection ===")
    for i, d in enumerate(input_details):
        print(f"[INPUT {i}]")
        print(f"  name:  {d['name']}")
        print(f"  shape: {d['shape']}")
        print(f"  dtype: {d['dtype']}")
        print(f"  quant: {d.get('quantization', None)}")

    for i, d in enumerate(output_details):
        print(f"[OUTPUT {i}]")
        print(f"  name:  {d['name']}")
        print(f"  shape: {d['shape']}")
        print(f"  dtype: {d['dtype']}")
        print(f"  quant: {d.get('quantization', None)}")

    return interpreter, input_details, output_details


def run_smoke_test(
    interpreter: tf.lite.Interpreter,
    input_details,
    output_details,
    input_size: int,
):
    input_info = input_details[0]
    output_info = output_details[0]

    x = np.random.uniform(
        0, 255, size=(1, input_size, input_size, 3)
    ).astype(np.float32)

    interpreter.set_tensor(input_info["index"], x)
    interpreter.invoke()
    y = interpreter.get_tensor(output_info["index"])

    print("\n=== Smoke test ===")
    print("Input batch shape:", x.shape)
    print("Input dtype:", x.dtype)
    print("Output shape:", y.shape)
    print("Output dtype:", y.dtype)

    flat = y.reshape(-1)
    print("Output first 10 values:", flat[:10])

    norm = np.linalg.norm(flat)
    print("Output L2 norm:", float(norm))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Download EfficientNet-Lite0 feature-vector from TF Hub and export "
            "to TFLite keeping current preprocessing semantics "
            "(raw 0..255 input + ImageNet mean/std normalization inside model)."
        )
    )
    parser.add_argument(
        "--hub-url",
        type=str,
        default=DEFAULT_HUB_URL,
        help="TF Hub URL for EfficientNet-Lite0 feature-vector",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("EfficientNetLite0.tflite"),
        help="Output TFLite file path",
    )
    parser.add_argument(
        "--input-size",
        type=int,
        default=DEFAULT_INPUT_SIZE,
        help="Input image size",
    )
    parser.add_argument(
        "--no-l2",
        action="store_true",
        help="Disable final L2 normalization",
    )
    parser.add_argument(
        "--quantization",
        type=str,
        default="float32",
        choices=["float32", "float16", "dynamic"],
        help="TFLite quantization mode",
    )
    args = parser.parse_args()

    print("TensorFlow version:", tf.__version__)
    print("TF Hub URL:", args.hub_url)
    print("Output:", args.output)
    print("Input size:", args.input_size)
    print("L2 normalize:", not args.no_l2)
    print("Quantization:", args.quantization)
    print("Preprocessing contract: raw 0..255 input + internal /255 + ImageNet mean/std")

    print("\n=== Building model ===")
    model = build_model(
        hub_url=args.hub_url,
        input_size=args.input_size,
        l2_normalize=not args.no_l2,
    )

    model.summary()

    print("\n=== Converting to TFLite ===")
    output_path = convert_to_tflite(
        model=model,
        output_path=args.output,
        quantization=args.quantization,
    )
    print(f"Saved TFLite model to: {output_path}")

    interpreter, input_details, output_details = inspect_tflite_model(output_path)

    out_shape = output_details[0]["shape"]
    if len(out_shape) == 2:
        print(f"\nOutput embedding dimension: {out_shape[-1]}")
    else:
        print(f"\nUnexpected output shape: {out_shape}")

    run_smoke_test(
        interpreter=interpreter,
        input_details=input_details,
        output_details=output_details,
        input_size=args.input_size,
    )


if __name__ == "__main__":
    main()