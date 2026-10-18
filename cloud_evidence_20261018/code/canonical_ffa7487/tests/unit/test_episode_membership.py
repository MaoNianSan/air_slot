from model.PRE.episode.membership import validate_episode_membership


def test_only_predecessor_and_successor_are_episode_members():
    assert validate_episode_membership("P", "P", "S")
    assert validate_episode_membership("S", "P", "S")
    assert not validate_episode_membership("X", "P", "S")
