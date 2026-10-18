# D4 FIXED_COMMON audit (2017 H1)

- Status: `PASS_FIXED_COMMON_REBUILT`
- Root: `artifacts\models\pre\PRE_MULTIYEAR_V1_D4_2017H1_R2`

| Check | Status | Detail |
|---|---|---|
| manifest_identity | PASS | dataset=data2_2017_2022, year=2017 |
| fit_window | PASS | {'end': '2017-06-30', 'start': '2017-01-01'} |
| admissibility | PASS | T100 H1 and DB1B Q1+Q2 |
| connection_share_artifact_hash | PASS | sha256:52ae53f829d5d35813c798be819cc4c9942e2d15f51c02534b5fb7090d678ee7 |
| connection_share_identity | PASS | dataset=data2_2017_2022, period=None |
| connection_share_manifest_hash | PASS | sha256:7a91df22705362a2465dbb020d483dea5b1ac088dc117d4edcaceff16b543723 |
| downstream_exposure_artifact_hash | PASS | sha256:1c740c0c5cafe88c591403b7210e8a869c2ba62816b86fea52459b916f32b615 |
| downstream_exposure_identity | PASS | dataset=data2_2017_2022, period=2017-H1 |
| downstream_exposure_manifest_hash | PASS | sha256:bde6d8923137228613db69f7d203ba86038d1330483e6852de20e5c0a8191c00 |
| expected_passengers_artifact_hash | PASS | sha256:825701691ac1619cafb5c1da479c114cb6ec85cf774a95ac9bfe58e849316049 |
| expected_passengers_identity | PASS | dataset=data2_2017_2022, period=None |
| expected_passengers_manifest_hash | PASS | sha256:42b994c9c14085e18731a973e24d9b7eef618624788c13cb233edb2b19d18388 |
| passenger_artifact_hash | PASS | sha256:b441dcef708f5f0df253c228ec4b5ada411d5bb26e6d3e51404fff2caf725580 |
| passenger_identity | PASS | dataset=data2_2017_2022, period=2017-H1 |
| passenger_manifest_hash | PASS | sha256:20d9442ba149cb6f05bf764d33108ef69b58862ecd3570931c4beb0e6b6febdb |
| taxi_artifact_hash | PASS | sha256:b93eaffef8535bf05ba63d524b9455cdf3470952cababb5981f090b083627c85 |
| taxi_identity | PASS | dataset=data2_2017_2022, period=2017-H1 |
| taxi_manifest_hash | PASS | sha256:083211b3145fddf8737da867d02a6a762022f9e5033210f4744b648a6c894c4f |
| turnaround_artifact_hash | PASS | sha256:89e7ef92511510da9e024e6a11a99fd0b33be26a4a06604eaf375f9ad3e1ce3e |
| turnaround_identity | PASS | dataset=data2_2017_2022, period=2017-H1 |
| turnaround_manifest_hash | PASS | sha256:728635291b03fcff650df3382bd9fa95dd9040d27af9e42adcc06766bd441597 |
| all_reference_kinds | PASS | found=['connection_share', 'downstream_exposure', 'expected_passengers', 'passenger', 'taxi', 'turnaround'] |
| scale_identity | PASS | dataset=data2_2017_2022, period=2017-H1 |
| scale_F_continuity | PASS | {'definition': 'max(0, R_IB - turnaround_reference(connection_airport))', 'median': 40.0, 'population_rows': 2055806, 'positive_n': 137394, 'unit': 'minutes'} |
| scale_F_execution | PASS | {'definition': 'D_OB', 'median': 17.0, 'population_rows': 2711358, 'positive_n': 979953, 'unit': 'minutes'} |
| scale_F_propagation | PASS | {'definition': 'D_TO * expected_downstream_exposure(origin)', 'median': 10.0, 'population_rows': 2711358, 'positive_n': 1756494, 'unit': 'exposure_minutes'} |
| scale_P_itinerary | PASS | {'definition': 'expected_passengers_per_flight * connection_share * I[D_TO > 45 minutes]', 'median': 11.45907189802828, 'population_rows': 2711358, 'positive_n': 273067, 'unit': 'expected_disrupted_connecting_passenger_exposure'} |
| scale_P_service | PASS | {'definition': 'expected_passengers_per_flight * I[D_TO >= 180 minutes]', 'median': 115.52173913043478, 'population_rows': 2711358, 'positive_n': 33886, 'unit': 'expected_long_delay_passenger_service_exposure'} |
| scale_P_time | PASS | {'definition': 'expected_passengers_per_flight * D_TO', 'median': 1022.3710247349823, 'population_rows': 2711358, 'positive_n': 1765272, 'unit': 'passenger_minutes'} |
| scale_R_operating | PASS | {'definition': 'D_TX', 'median': 5.0, 'population_rows': 2711358, 'positive_n': 1249042, 'unit': 'excess_taxi_minutes'} |
| scale_bundle_hash | PASS | sha256:9cd696aafb87bae6e3fc3872b178b980fcd5647ce21d23bc23d7c1d429774abd |
