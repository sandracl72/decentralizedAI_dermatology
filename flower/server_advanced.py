import flwr as fl 
from typing import List, Tuple, Dict, Optional
import sys, os
import numpy as np
sys.path.append('/workspace/stylegan2-ada-pytorch') 
import torch
import torch.nn as nn 
from collections import OrderedDict
import utils
import warnings

from argparse import ArgumentParser 

warnings.filterwarnings("ignore")

DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# TODO: Abstract load data, load model, train etc in utils.py


def set_parameters(model, parameters: List[np.ndarray]) -> None:
        # Set model parameters from a list of NumPy ndarrays
        keys = [k for k in model.state_dict().keys() if 'bn' not in k]
        params_dict = zip(keys, parameters)
        state_dict = OrderedDict({k: torch.tensor(v) for k, v in params_dict})
        model.load_state_dict(state_dict, strict=False)

def get_eval_fn(model):
    """Return an evaluation function for server-side evaluation."""

    # Load data and model here to avoid the overhead of doing it in `evaluate` itself
    _, testloader, _ = utils.load_isic_data()

    # The `evaluate` function will be called after every round
    def evaluate(
        weights: fl.common.Weights,
    ) -> Optional[Tuple[float, Dict[str, fl.common.Scalar]]]:
        # Update model with the latest parameters
        set_parameters(model, weights) 
        loss, auc, accuracy, f1 = utils.val(model, testloader, criterion = nn.BCEWithLogitsLoss())
        return float(loss), {"accuracy": float(accuracy), "auc": float(auc)}

    return evaluate


def fit_config(rnd: int):
    """Return training configuration dict for each round.
    Keep batch size fixed at 32, perform two rounds of training with one
    local epoch, increase to two local epochs afterwards.
    """
    config = {
        "batch_size": 32,
        "local_epochs": 1 if rnd < 2 else 2,
    }
    return config


def evaluate_config(rnd: int):
    """Return evaluation configuration dict for each round.
    Perform five local evaluation steps on each client (i.e., use five
    batches) during rounds one to three, then increase to ten local
    evaluation steps.
    """
    val_steps = 5 if rnd < 4 else 10
    return {"val_steps": val_steps}



if __name__ == "__main__":

    parser = ArgumentParser()  
    parser.add_argument("--model", type=str, default='efficientnet')
    args = parser.parse_args()

    # Load model for
        # 1. server-side parameter initialization
        # 2. server-side parameter evaluation
    model = utils.load_model(args.model)
    model_weights = [val.cpu().numpy() for name, val in model.state_dict().items()  if 'bn' not in name]

    
    # Create strategy
    strategy = fl.server.strategy.FedAvg(
        fraction_fit=1,
        fraction_eval=1,
        min_fit_clients=2,
        min_eval_clients=2,
        min_available_clients=2,
        eval_fn=get_eval_fn(model),
        on_fit_config_fn=fit_config,
        on_evaluate_config_fn=evaluate_config,
        initial_parameters=fl.common.weights_to_parameters(model_weights), 
    )

    fl.server.start_server("0.0.0.0:8080", config={"num_rounds": 5}, strategy=strategy)