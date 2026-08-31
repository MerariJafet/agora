from agora_api import ids


def test_namespaces():
    assert ids.new_agent_id().startswith("agt_")
    assert ids.new_device_id().startswith("dev_")
    assert ids.new_event_id().startswith("evt_")
    assert ids.new_challenge_id().startswith("chl_")
    assert ids.new_agent_version_id().startswith("agv_")
    assert ids.new_user_id().startswith("usr_")
    assert ids.new_wallet_id().startswith("wal_")
    assert ids.new_tokoin_entry_id().startswith("tko_")
    assert ids.new_tokoin_block_id().startswith("tkb_")
    assert ids.new_tokoin_authorization_id().startswith("txa_")
    assert ids.new_opportunity_id().startswith("opp_")
    assert ids.new_need_id().startswith("ned_")
    assert ids.new_offer_id().startswith("off_")
    assert ids.new_commitment_id().startswith("cmt_")
    assert ids.new_contribution_id().startswith("ctb_")
    assert ids.new_outcome_id().startswith("out_")


def test_ids_are_sortable_by_time():
    first = ids.new_event_id()
    second = ids.new_event_id()
    assert first < second  # ULIDs sort by creation time


def test_validation():
    agent_id = ids.new_agent_id()
    assert ids.is_valid(agent_id, "agt")
    assert not ids.is_valid(agent_id, "dev")
    assert not ids.is_valid("agt_short")
    assert not ids.is_valid("hacker_input")
