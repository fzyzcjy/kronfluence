import logging

import numpy as np
import torch
from scipy.stats import spearmanr

from kronfluence.analyzer import Analyzer


def main():
    logging.basicConfig(level=logging.INFO)

    results = torch.load("files/lds_results.pt")
    diff_loss = torch.from_numpy(results["diff_loss"])
    mask = torch.from_numpy(results["mask"]).float()
    mask = ((mask + 1) % 2).to(dtype=torch.float64).t()

    scores = Analyzer.load_file("scores_pairwise/pairwise_scores.safetensors")["all_modules"].to(dtype=torch.float64)
    preds = (scores @ mask).t().numpy()

    corr_lst = []
    for i in range(120):
        corr_lst.append(spearmanr(diff_loss[:, i], preds[:, i])[0])
    print(np.mean(corr_lst))


if __name__ == "__main__":
    main()
