#!/usr/bin/env python
# coding: utf-8
from biome.text import Dataset
from biome.text.hpo import TuneExperiment
from ray import tune


train_ds = Dataset.from_json("/home/ec2-user/biome/profner/preprocessing_inference/train_v1.json")
valid_ds = Dataset.from_json("/home/ec2-user/biome/profner/preprocessing_inference/valid_v1.json")


train_ds.rename_column_("tags_bio", "tags")
valid_ds.rename_column_("tags_bio", "tags")
train_ds.rename_column_("classification_label", "labels")
valid_ds.rename_column_("classification_label", "labels")


# This is the config of a second HPO run, a
# fter a first HPO run we fixed obviously better choices like:
# the weights_file, lowercase_characters, some RNN types and num_layers
profner = {
    "name": "profner",
    "features": {
        "word": {
            "embedding_dim": 300, 
            "weights_file": "/home/ec2-user/biome/covid_19_es_twitter_skipgram_cased.vec",
            "trainable": True,
        },
        'char': {
            'embedding_dim': tune.choice([32, 64]),
            'lowercase_characters': True,
            'encoder': {
                'bidirectional': True,
                'hidden_size': tune.choice([32, 64]),
                'num_layers': 1,
                'type': 'gru',
            },
            'dropout': tune.uniform(0, 0.5),
        },
    },
    "encoder": {
        "type": tune.choice(["gru", "lstm"]),
        "num_layers": 1,
        "bidirectional": True,
        "hidden_size": tune.choice([256, 512]),
    },
    "head": {
        "type": "ProfNer",
        "classification_labels": ['1', '0'],
        "classification_pooler": {
            "type": "lstm",
            "num_layers": 1,
            "bidirectional": True,
            "hidden_size": tune.choice([64, 128]),
        },
        "ner_feedforward": {
            "activations": ["relu"],
            "dropout": [0],
            "hidden_dims": [128],
            "num_layers": 1,
        },
        "ner_tags": ['O', 'B-PROFESION', 'I-SITUACION_LABORAL', 'I-PROFESION', 'B-SITUACION_LABORAL'],
        "ner_tags_encoding": "BIO",
        "dropout": tune.uniform(0, 0.7),
    },
}

trainer_config = dict(
    optimizer={
        "type": "adamw",
        "lr": tune.loguniform(1e-4, 1e-1),
        "weight_decay": tune.loguniform(1e-3, 1e-1)
    },
    linear_decay=True,
    warmup_steps=tune.randint(0, 200),
    training_size=len(train_ds),
    batch_size=tune.choice([8, 16, 32]),
    num_epochs=tune.choice([4, 5, 6, 7]),
    validation_metric="+valid_ner/f1-measure-overall"
)


from ray.tune.suggest.hyperopt import HyperOptSearch
search_alg = HyperOptSearch(metric="validation_ner/f1-measure-overall", mode="max")

# does not support integers
# from ray.tune.suggest.bayesopt import BayesOptSearch
# search_alg = BayesOptSearch(metric="validation_ner/f1-measure-overall", mode="max")

# ray2.0.0 does not use the gpu ...
# from ray.tune.suggest.hebo import HEBOSearch
# search_alg = HEBOSearch(metric="validation_ner/f1-measure-overall", mode="max")


random_search = TuneExperiment(
    pipeline_config=profner,
    trainer_config=trainer_config,
    train_dataset=train_ds,
    valid_dataset=valid_ds,
    name="profner_rnn",
    num_samples=200,
    local_dir="tune_runs",
    resources_per_trial={"cpu": 1, "gpu": 0.33},
)


analysis = tune.run(
    random_search,
    config=random_search.config,
    scheduler=tune.schedulers.ASHAScheduler(),
    search_alg=search_alg,
    metric="validation_valid_ner/f1-measure-overall",
    mode="max",
    progress_reporter=tune.CLIReporter(
            metric_columns=["best_validation_valid_ner/f1-measure-overall", "best_validation_valid_classification/accuracy"],
            parameter_columns=["trainer.optimizer.lr"],
        ),
    # progress_reporter=tune.JupyterNotebookReporter(overwrite=True)
    verbose=2,
)
