from pathlib import Path
import argparse

from AI_classification.training.train_script import create_training_index_with_tflite


def main():
    parser = argparse.ArgumentParser(
        description="Build TFLite/mobile JSON index."
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tour-id", type=int, default=3)
    args = parser.parse_args()

    create_training_index_with_tflite(
        tflite_model_path=args.model,
        dataset_root=args.dataset,
        output_json=args.output,
        tour_id=args.tour_id,
    )


if __name__ == "__main__":
    main()