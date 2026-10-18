import torch
from model.M1.contracts import TargetBinContract
from model.M1.network import OrderedEventGRU
from model.M1.loss import interval_nll

def test_ordered_one_layer_heads_and_interval_marginalization():
    bins = {n:TargetBinContract(target_name=n, bin_width_minutes=5, max_finite_minutes=20) for n in ("R_IB","R_OB","T_TX")}
    model = OrderedEventGRU(input_size=10, hidden_size=8, bins=bins)
    assert model.gru.num_layers == 1 and not model.gru.bidirectional
    logits = model(torch.randn(2,4,10), torch.tensor([4,3]), teacher={"R_IB":torch.tensor([1,2]),"R_OB":torch.tensor([2,1])})
    assert all(logits[n].shape == (2,6) for n in bins)
    loss = interval_nll(logits["R_IB"], bins["R_IB"], lower=torch.tensor([5.,7.]), upper=torch.tensor([10.,13.]), active=torch.tensor([True,False]))
    assert torch.isfinite(loss)
