# pylint: skip-file

from typing import Optional

import pytest
import torch
from scipy.stats import spearmanr

from kronfluence.arguments import ScoreArguments
from kronfluence.utils.common.factor_arguments import test_factor_arguments
from kronfluence.utils.common.score_arguments import test_score_arguments
from kronfluence.utils.constants import ALL_MODULE_NAME
from kronfluence.utils.dataset import DataLoaderKwargs
from tests.utils import (
    ATOL,
    DEFAULT_FACTORS_NAME,
    DEFAULT_SCORES_NAME,
    RTOL,
    check_tensor_dict_equivalence,
    custom_scores_name,
    prepare_model_and_analyzer,
    prepare_test,
)


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "repeated_mlp",
        "conv",
        "bert",
        "roberta",
        "gpt",
        "gpt_checkpoint",
    ],
)
@pytest.mark.parametrize("score_dtype", [torch.float32, torch.bfloat16])
@pytest.mark.parametrize("query_gradient_rank", [None, 16])
@pytest.mark.parametrize("query_size", [16])
@pytest.mark.parametrize("train_size", [32])
@pytest.mark.parametrize("seed", [0])
def test_compute_pairwise_scores(
    test_name: str,
    score_dtype: torch.dtype,
    query_gradient_rank: Optional[int],
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Makes sure that the pairwise influence computations are working properly.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )
    factor_args = test_factor_arguments()
    if test_name == "repeated_mlp":
        factor_args.shared_parameters_exist = True

    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        factor_args=factor_args,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=32,
        overwrite_output_dir=True,
    )

    score_args = ScoreArguments(
        score_dtype=score_dtype,
        query_gradient_rank=query_gradient_rank,
    )
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )

    pairwise_scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)
    assert pairwise_scores[ALL_MODULE_NAME].size(0) == query_size
    assert pairwise_scores[ALL_MODULE_NAME].size(1) == train_size
    assert pairwise_scores[ALL_MODULE_NAME].dtype == score_dtype


@pytest.mark.parametrize("test_name", ["mlp"])
@pytest.mark.parametrize("per_sample_gradient_dtype", [torch.float32, torch.bfloat16])
@pytest.mark.parametrize("precondition_dtype", [torch.float32, torch.bfloat16])
@pytest.mark.parametrize("score_dtype", [torch.float32, torch.bfloat16])
@pytest.mark.parametrize("query_gradient_rank", [None, 16])
@pytest.mark.parametrize("damping", [None, 1e-08])
@pytest.mark.parametrize("query_size", [16])
@pytest.mark.parametrize("train_size", [32])
@pytest.mark.parametrize("seed", [6])
def test_compute_pairwise_scores_dtype(
    test_name: str,
    per_sample_gradient_dtype: torch.dtype,
    precondition_dtype: torch.dtype,
    score_dtype: torch.dtype,
    query_gradient_rank: Optional[int],
    damping: Optional[float],
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Makes sure that the pairwise influence computations are working properly with different dtypes.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )
    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=32,
        overwrite_output_dir=True,
    )

    score_args = ScoreArguments(
        damping=damping,
        score_dtype=score_dtype,
        query_gradient_rank=query_gradient_rank,
        per_sample_gradient_dtype=per_sample_gradient_dtype,
        precondition_dtype=precondition_dtype,
    )
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )

    pairwise_scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)
    assert pairwise_scores[ALL_MODULE_NAME].size(0) == query_size
    assert pairwise_scores[ALL_MODULE_NAME].size(1) == train_size
    assert pairwise_scores[ALL_MODULE_NAME].dtype == score_dtype


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "conv_bn",
    ],
)
@pytest.mark.parametrize("strategy", ["identity", "diagonal", "kfac", "ekfac"])
@pytest.mark.parametrize("query_size", [20])
@pytest.mark.parametrize("train_size", [50])
@pytest.mark.parametrize("seed", [1])
def test_pairwise_scores_batch_size_equivalence(
    test_name: str,
    strategy: str,
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Pairwise influence scores should be identical regardless of what batch size used.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    model = model.to(dtype=torch.float64)
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )

    factor_args = test_factor_arguments(strategy=strategy)
    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=4,
        factor_args=factor_args,
        overwrite_output_dir=True,
    )

    score_args = test_score_arguments()
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=1,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    bs1_scores = analyzer.load_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
    )

    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name("bs8"),
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=3,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    bs8_scores = analyzer.load_pairwise_scores(
        scores_name=custom_scores_name("bs8"),
    )

    assert check_tensor_dict_equivalence(
        bs1_scores,
        bs8_scores,
        atol=ATOL,
        rtol=RTOL,
    )

    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name("auto"),
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=10,
        train_dataset=train_dataset,
        per_device_train_batch_size=None,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    bs_auto_scores = analyzer.load_pairwise_scores(
        scores_name=custom_scores_name("auto"),
    )

    assert check_tensor_dict_equivalence(
        bs1_scores,
        bs_auto_scores,
        atol=ATOL,
        rtol=RTOL,
    )


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "conv",
    ],
)
@pytest.mark.parametrize("data_partition_size", [1, 4])
@pytest.mark.parametrize("module_partition_size", [1, 3])
@pytest.mark.parametrize("per_module_score", [True, False])
@pytest.mark.parametrize("query_size", [32])
@pytest.mark.parametrize("train_size", [64])
@pytest.mark.parametrize("seed", [2])
def test_pairwise_scores_partition_equivalence(
    test_name: str,
    data_partition_size: int,
    module_partition_size: int,
    per_module_score: bool,
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Influence scores should be identical regardless of what the partition used.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    model = model.to(dtype=torch.float64)
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )

    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=8,
        overwrite_output_dir=True,
    )

    score_args = test_score_arguments()
    score_args.per_module_score = per_module_score
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)

    score_args.data_partition_size = data_partition_size
    score_args.module_partition_size = module_partition_size
    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name(f"{data_partition_size}_{module_partition_size}"),
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=10,
        train_dataset=train_dataset,
        per_device_train_batch_size=5,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    partitioned_scores = analyzer.load_pairwise_scores(
        scores_name=custom_scores_name(f"{data_partition_size}_{module_partition_size}"),
    )

    assert check_tensor_dict_equivalence(
        scores,
        partitioned_scores,
        atol=ATOL,
        rtol=RTOL,
    )


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "conv",
        "gpt",
    ],
)
@pytest.mark.parametrize("query_size", [32])
@pytest.mark.parametrize("train_size", [64])
@pytest.mark.parametrize("seed", [0])
def test_per_module_scores_equivalence(
    test_name: str,
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Influence scores should be identical with and without per module score computations.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    model = model.to(dtype=torch.float64)
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )

    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=8,
        overwrite_output_dir=True,
    )

    score_args = test_score_arguments()
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)

    score_args.per_module_score = True
    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name("per_module"),
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    per_module_scores = analyzer.load_pairwise_scores(scores_name=custom_scores_name("per_module"))

    total_scores = None
    for module_name in per_module_scores:
        if total_scores is None:
            total_scores = per_module_scores[module_name]
        else:
            total_scores.add_(per_module_scores[module_name])

    assert torch.allclose(total_scores, scores[ALL_MODULE_NAME], atol=ATOL, rtol=RTOL)


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "conv_bn",
    ],
)
@pytest.mark.parametrize("query_size", [60])
@pytest.mark.parametrize("train_size", [60])
@pytest.mark.parametrize("seed", [2])
def test_compute_pairwise_scores_with_indices(
    test_name: str,
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Makes sure the indices selection is correctly implemented.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        train_size=train_size,
        query_size=query_size,
        seed=seed,
    )
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )
    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=32,
        overwrite_output_dir=True,
    )

    score_args = test_score_arguments()
    score_args.data_partition_size = 2
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        query_indices=list(range(30)),
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        train_indices=list(range(50)),
        per_device_train_batch_size=8,
        score_args=score_args,
        dataloader_kwargs=kwargs,
        overwrite_output_dir=True,
    )

    pairwise_scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)
    assert pairwise_scores[ALL_MODULE_NAME].size(0) == 30
    assert pairwise_scores[ALL_MODULE_NAME].size(1) == 50


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "conv_bn",
    ],
)
@pytest.mark.parametrize("query_size", [64])
@pytest.mark.parametrize("train_size", [32])
@pytest.mark.parametrize("num_query_gradient_accumulations", [2, 5])
@pytest.mark.parametrize("seed", [5])
def test_query_accumulation(
    test_name: str,
    query_size: int,
    train_size: int,
    num_query_gradient_accumulations: int,
    seed: int,
) -> None:
    # Makes sure the query accumulation is correctly implemented.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    model = model.to(dtype=torch.float64)
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )

    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=8,
        overwrite_output_dir=True,
    )

    score_args = test_score_arguments(query_gradient_rank=8)
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)

    score_args.num_query_gradient_accumulations = num_query_gradient_accumulations
    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name("accumulation"),
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=10,
        train_dataset=train_dataset,
        per_device_train_batch_size=5,
        dataloader_kwargs=kwargs,
        score_args=score_args,
        overwrite_output_dir=True,
    )
    partitioned_scores = analyzer.load_pairwise_scores(
        scores_name=custom_scores_name("accumulation"),
    )

    assert check_tensor_dict_equivalence(
        scores,
        partitioned_scores,
        atol=ATOL,
        rtol=RTOL,
    )


@pytest.mark.parametrize(
    "test_name",
    [
        "mlp",
        "conv",
    ],
)
@pytest.mark.parametrize("query_size", [50])
@pytest.mark.parametrize("train_size", [32])
@pytest.mark.parametrize("seed", [8])
def test_pairwise_shared_parameters(
    test_name: str,
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Makes sure the scores are identical with and without `shared_parameters_exist` flag.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    model = model.to(dtype=torch.float64)
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )
    factor_args = test_factor_arguments()
    factor_args.shared_parameters_exist = False
    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        factor_args=factor_args,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=8,
        overwrite_output_dir=True,
    )
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        overwrite_output_dir=True,
    )
    scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)

    factor_args.shared_parameters_exist = True
    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        factor_args=factor_args,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=8,
        overwrite_output_dir=True,
    )
    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name("shared"),
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        overwrite_output_dir=True,
    )
    shared_scores = analyzer.load_pairwise_scores(scores_name=custom_scores_name("shared"))

    assert check_tensor_dict_equivalence(
        scores,
        shared_scores,
        atol=ATOL,
        rtol=RTOL,
    )


@pytest.mark.parametrize(
    "test_name",
    ["mlp", "conv_bn", "gpt"],
)
@pytest.mark.parametrize("query_gradient_rank", [16, 32])
@pytest.mark.parametrize("use_full_svd", [False, True])
@pytest.mark.parametrize("num_query_gradient_accumulations", [1, 3])
@pytest.mark.parametrize("query_size", [64])
@pytest.mark.parametrize("train_size", [160])
@pytest.mark.parametrize("seed", [9])
def test_pairwise_query_batching(
    test_name: str,
    query_gradient_rank: int,
    use_full_svd: bool,
    num_query_gradient_accumulations: int,
    query_size: int,
    train_size: int,
    seed: int,
) -> None:
    # Makes sure similar results are obtained with and without query batching.
    model, train_dataset, test_dataset, data_collator, task = prepare_test(
        test_name=test_name,
        query_size=query_size,
        train_size=train_size,
        seed=seed,
    )
    model = model.to(dtype=torch.float64)
    kwargs = DataLoaderKwargs(collate_fn=data_collator)
    model, analyzer = prepare_model_and_analyzer(
        model=model,
        task=task,
    )
    factor_args = test_factor_arguments()
    analyzer.fit_all_factors(
        factors_name=DEFAULT_FACTORS_NAME,
        factor_args=factor_args,
        dataset=train_dataset,
        dataloader_kwargs=kwargs,
        per_device_batch_size=8,
        overwrite_output_dir=True,
    )
    score_args = test_score_arguments()
    analyzer.compute_pairwise_scores(
        scores_name=DEFAULT_SCORES_NAME,
        score_args=score_args,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=4,
        train_dataset=train_dataset,
        per_device_train_batch_size=8,
        dataloader_kwargs=kwargs,
        overwrite_output_dir=True,
    )
    scores = analyzer.load_pairwise_scores(scores_name=DEFAULT_SCORES_NAME)

    score_args.query_gradient_rank = query_gradient_rank
    score_args.use_full_svd = use_full_svd
    score_args.num_query_gradient_accumulations = num_query_gradient_accumulations
    analyzer.compute_pairwise_scores(
        scores_name=custom_scores_name("qb"),
        score_args=score_args,
        factors_name=DEFAULT_FACTORS_NAME,
        query_dataset=test_dataset,
        per_device_query_batch_size=3,
        train_dataset=train_dataset,
        per_device_train_batch_size=9,
        dataloader_kwargs=kwargs,
        overwrite_output_dir=True,
    )
    qb_scores = analyzer.load_pairwise_scores(scores_name=custom_scores_name("qb"))

    for i in range(query_size):
        assert spearmanr(scores[ALL_MODULE_NAME][i], qb_scores[ALL_MODULE_NAME][i])[0] > 0.9
