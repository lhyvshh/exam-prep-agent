from exam_prep.packages.frm_policy import FRM_PART_I_POLICY


def test_frm_part_i_major_domain_weights_and_three_exam_counts() -> None:
    policy = FRM_PART_I_POLICY
    assert policy.domain_weights == {
        "Foundations of Risk Management": 20,
        "Quantitative Analysis": 20,
        "Financial Markets and Products": 30,
        "Valuation and Risk Models": 30,
    }
    assert [sum(exam.values()) for exam in policy.exam_domain_counts] == [100, 100, 100]
    assert all(dict(exam) == dict(policy.domain_weights) for exam in policy.exam_domain_counts)
    assert {
        domain: sum(exam[domain] for exam in policy.exam_domain_counts)
        for domain in policy.domain_weights
    } == {
        "Foundations of Risk Management": 60,
        "Quantitative Analysis": 60,
        "Financial Markets and Products": 90,
        "Valuation and Risk Models": 90,
    }


def test_frm_part_i_fallback_profiles_each_total_one_hundred() -> None:
    policy = FRM_PART_I_POLICY
    assert sum(policy.question_type_counts.values()) == 100
    assert [sum(profile.values()) for profile in policy.difficulty_counts] == [100, 100, 100]
    assert {domain: sum(counts.values()) for domain, counts in policy.subtopic_counts.items()} == (
        policy.domain_weights
    )
