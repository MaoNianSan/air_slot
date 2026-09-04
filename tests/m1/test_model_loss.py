import torch
from model.M1.contracts import TargetBinContract
from model.M1.model_layer.gru import OrderedEventGRU
from model.M1.loss import interval_nll

def test_ordered_one_layer_heads_and_interval_marginalization():
    bins = {
        "R_IB": TargetBinContract(target_name="R_IB", bin_width_minutes=5, max_finite_minutes=20),
        "DELTA_OB": TargetBinContract(target_name="DELTA_OB", bin_width_minutes=5,
                                        min_finite_minutes=-20, max_finite_minutes=20, signed=True),
        "T_TX": TargetBinContract(target_name="T_TX", bin_width_minutes=5, max_finite_minutes=20),
    }
    model = OrderedEventGRU(input_size=10, hidden_size=8, bins=bins)
    assert model.gru.num_layers == 1 and not model.gru.bidirectional
    logits = model(torch.randn(2,4,10), torch.tensor([4,3]), teacher={"R_IB":torch.tensor([1,2]),"DELTA_OB":torch.tensor([2,1])})
    assert logits["DELTA_OB"].shape == (2, 11)
    assert logits["R_IB"].shape == logits["T_TX"].shape == (2, 6)
    loss = interval_nll(logits["R_IB"], bins["R_IB"], lower=torch.tensor([5.,7.]), upper=torch.tensor([10.,13.]), active=torch.tensor([True,False]))
    assert torch.isfinite(loss)
