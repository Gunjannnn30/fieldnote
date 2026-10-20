# Fieldnote eval report

## 1. Headline

| metric | fieldnote | caption-only baseline | delta |
|---|---|---|---|
| accuracy, all 40 questions | 100.0% | 60.0% | 40.0% |
| **accuracy, 15 picture-only questions** | **100.0%** | 0.0% | **100.0%** |
| accuracy, 25 text-answerable questions | 100.0% | 96.0% | 4.0% |


## 2. Latency

| latency (ms, end to end) | p50 | p95 | p99 | mean | max |
|---|---|---|---|---|---|
| fieldnote | 1607.0 | 1985.5 | 2205.6 | 1583.6 | 2205.6 |
| caption-only baseline | 1275.3 | 2506.3 | 30086.9 | 2098.3 | 30086.9 |


## 3. Citation compliance

| citation compliance | fieldnote | caption-only baseline |
|---|---|---|
| answers carrying a page number | 36/40 | 40/40 |
| answers carrying a cropped image | 40/40 | 0/40 |
| citation points at the right page | 90.0% | 87.5% |


## 4. Which modality supplied the answer

| modality that supplied the winning evidence | fieldnote | caption-only baseline |
|---|---|---|
| audio | 5 | 6 |
| image | 11 | 0 |
| text | 24 | 34 |


## 5. The 15 picture-only questions

| qid | question | expected | fieldnote answer | baseline answer |
|---|---|---|---|---|
| I01 | What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve? | `385` | **PASS** 385 (385 PSI) | fail Install a 1/8 in. rated filter drier in the liquid line between the co |
| I02 | What is the low-pressure cutout pressure labeled on the R-410A pressure-temperature curve? | `92` | **PASS** 92 (92 PSI) | fail Install a 1/8 in. rated filter drier in the liquid line between the co |
| I03 | What peak discharge pressure is labeled on the R-410A pressure-temperature curve? | `425` | **PASS** 425 (425 PSIG) | fail Install a 1/8 in. rated filter drier in the liquid line between the co |
| I04 | What superheat setpoint is labeled on the TXV superheat adjustment chart? | `18` | **PASS** SETPOINT-18-DEG-F | fail Torque the setpoint screw on the YK thermostat to 6 in. lb after adjus |
| I05 | What maximum amp draw is labeled on the 5-ton performance chart? | `32.5` | **PASS** MAX 4 AMPS 32.5 A | fail Set the supply air total external static pressure to 0.75 in. w.c. Thi |
| I06 | What subcooling target is labeled on the subcooling verification chart? | `16` | **PASS** 16 (TARGET 16 DEGF) | fail Figure 9. Subcooling verification at rated load. |
| I07 | What field supply voltage is printed on the YSC072 unit 7 wiring diagram? | `240V 3PH 60HZ` | **PASS** FIELD SUPPLY 240 V 3PH 60 HZ | fail Set the cooling temperature differential to 4°F for the standard YSC07 |
| I08 | What disconnect rating is printed on the YSC072 unit 7 wiring diagram? | `60A` | **PASS** 60 (DISCONNECT 60A) | fail During startup the unit disconnect must show at least 187V on a 208V s |
| I09 | What high-pressure switch setpoint is printed on the unit 7 wiring diagram? | `600 PSI` | **PASS** 600 (HP SWITCH 600 PSI) | fail Hi, I've got a rooftop unit that keeps tripping on high pressure. |
| I10 | What minimum supply air temperature is listed in the coil capacity table? | `55°F` | **PASS** 55 (55 DEG F) | fail Set the supply air total external static pressure to 0.75 in. w.c. Thi |
| I11 | What maximum indoor airflow is listed in the 6-ton capacity table? | `2400 CFM` | **PASS** 2400 (2400 CFM) | fail Set the supply air total external static pressure to 0.75 in. w.c. Thi |
| I12 | What model number is stamped on the nameplate in the job site photo? | `NP-42` | **PASS** MODEL NP-42 | fail I need to see the nameplate on the unit to confirm the model and the r |
| I13 | What supply voltage is stamped on the data plate in the job site photo? | `460V` | **PASS** VOLTAGE 460 V 3 PH 60 HZ | fail All YK series controls operate on 24V control power supplied from the  |
| I14 | What pressure does the gauge in the job site photo read? | `312` | **PASS** 312 (312 PSI) | fail Set the supply air total external static pressure to 0.75 in. w.c. Thi |
| I15 | What fault code is displayed on the control board in the job site photo? | `LP-2` | **PASS** FAULT LP-2 | fail All YK series controls operate on 24V control power supplied from the  |


## 6. All 40 questions

| qid | question | expected | fieldnote | baseline | evidence modality | citation | fieldnote answer |
|---|---|---|---|---|---|---|---|
| A01 | Which roof was the unit that kept tripping on high pressure located on? | `roof B` | **PASS** | PASS | audio | aud:call_unit7_hp_trip | It's on roof B, at the back of the building, next to the stairwell mechanical room. |
| A02 | What temperature did the technician say it was outside during the support call? | `97°F` | **PASS** | PASS | audio | aud:call_unit7_hp_trip | The thermostat was set to 72 degrees and it was 97 degrees outside. |
| A03 | What did the support line tell the technician to photograph and send back? | `the nameplate` | **PASS** | fail | audio | aud:call_unit7_hp_trip | I will go photograph the nameplate and send it in. |
| A04 | What did the technician say had a brown crust on it? | `brown crust` | **PASS** | PASS | audio | aud:call_nameplate_mismatch | There is a brown crust on two of them. |
| I01 | What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve? | `385` | **PASS** | fail | image | p.11 | 385 (385 PSI) |
| I02 | What is the low-pressure cutout pressure labeled on the R-410A pressure-temperature curve? | `92` | **PASS** | fail | image | p.11 | 92 (92 PSI) |
| I03 | What peak discharge pressure is labeled on the R-410A pressure-temperature curve? | `425` | **PASS** | fail | image | p.11 | 425 (425 PSIG) |
| I04 | What superheat setpoint is labeled on the TXV superheat adjustment chart? | `18` | **PASS** | fail | text | p.9 | SETPOINT-18-DEG-F |
| I05 | What maximum amp draw is labeled on the 5-ton performance chart? | `32.5` | **PASS** | fail | text | p.10 | MAX 4 AMPS 32.5 A |
| I06 | What subcooling target is labeled on the subcooling verification chart? | `16` | **PASS** | fail | text | p.7 | 16 (TARGET 16 DEGF) |
| I07 | What field supply voltage is printed on the YSC072 unit 7 wiring diagram? | `240V 3PH 60HZ` | **PASS** | fail | image | p.12 | FIELD SUPPLY 240 V 3PH 60 HZ |
| I08 | What disconnect rating is printed on the YSC072 unit 7 wiring diagram? | `60A` | **PASS** | fail | image | p.12 | 60 (DISCONNECT 60A) |
| I09 | What high-pressure switch setpoint is printed on the unit 7 wiring diagram? | `600 PSI` | **PASS** | fail | image | p.12 | 600 (HP SWITCH 600 PSI) |
| I10 | What minimum supply air temperature is listed in the coil capacity table? | `55°F` | **PASS** | fail | image | p.11 | 55 (55 DEG F) |
| I11 | What maximum indoor airflow is listed in the 6-ton capacity table? | `2400 CFM` | **PASS** | fail | image | p.11 | 2400 (2400 CFM) |
| I12 | What model number is stamped on the nameplate in the job site photo? | `NP-42` | **PASS** | fail | audio | aud:call_unit7_hp_trip | MODEL NP-42 |
| I13 | What supply voltage is stamped on the data plate in the job site photo? | `460V` | **PASS** | fail | image | img:job_photo_unit_7_nameplate | VOLTAGE 460 V 3 PH 60 HZ |
| I14 | What pressure does the gauge in the job site photo read? | `312` | **PASS** | fail | image | img:job_photo_suction_gauge | 312 (312 PSI) |
| I15 | What fault code is displayed on the control board in the job site photo? | `LP-2` | **PASS** | fail | image | img:job_photo_control_board | FAULT LP-2 |
| T01 | What is the required filter differential pressure for the YSC072 economizer? | `0.5 in. w.c.` | **PASS** | PASS | text | p.3 | The required filter differential pressure for this unit is 0.5 in. w.c. measured across th |
| T02 | What supply air total external static pressure should the YSC072 be set to? | `0.75 in. w.c.` | **PASS** | PASS | text | p.4 | Set the supply air total external static pressure to 0.75 in. w.c. This value is the desig |
| T03 | How long must the YSC072 be operated before the subcooling is checked? | `15 minutes` | **PASS** | PASS | text | p.5 | Operate the unit with the doors open and the economizer disabled for 15 minutes before rea |
| T04 | What is the required nitrogen purge duration before brazing on a R-410A line set? | `10 minutes` | **PASS** | PASS | text | p.6 | Flow dry nitrogen through the line set at a minimum of 2 scfh for 10 minutes before the to |
| T05 | What is the minimum clearance between the outdoor coil and an obstruction? | `12 inches` | **PASS** | PASS | text | p.7 | Maintain a minimum clearance of 12 inches between the outdoor coil face and any obstructio |
| T06 | What torque is specified for the YSC072 compressor terminal cover screws? | `12 in. lb` | **PASS** | PASS | text | p.8 | Torque the terminal cover screws to 12 in. lb when reinstalling the cover |
| T07 | What is the maximum supply air temperature drop in YSC072 dehumidification mode? | `20°F` | **PASS** | PASS | text | p.9 | In dehumidification mode the unit controls the supply air leaving the evaporator to a maxi |
| T08 | What liquid line filter size is specified for a 5-ton R-410A 48TC circuit? | `1/8 in.` | **PASS** | PASS | text | p.3 | Install a 1/8 in. rated filter drier in the liquid line between the condensing unit and th |
| T09 | What branch circuit size is required for the 208V single-phase 3-ton 48TC? | `40A` | **PASS** | PASS | text | p.4 | The 208V single-phase 3-ton unit requires a 40A branch circuit with copper conductors size |
| T10 | What is the factory charge weight of the 3-ton Carrier 48TC using R-410A? | `8.5 lb` | **PASS** | PASS | text | p.5 | The factory charge for the 3-ton unit using R-410A is 8.5 lb. Field added refrigerant must |
| T11 | How many filters does the Carrier 48TC filter rack accept? | `4` | **PASS** | PASS | text | p.6 | The filter rack accepts 4 standard 2-inch pleated filters in the standard 48TC cabinet |
| T12 | What is the minimum acceptable voltage at the unit disconnect during startup? | `187V` | **PASS** | PASS | text | p.7 | During startup the unit disconnect must show at least 187V on a 208V system |
| T13 | What is the required condensing temperature approach above ambient on the XC14? | `5°F` | **PASS** | PASS | text | p.5 | The condensing temperature should run 5°F above the outdoor ambient temperature at steady  |
| T14 | What superheat range should a thermostatic expansion valve system hold at rated load? | `8°F to 12°F` | **PASS** | PASS | text | p.4 | A thermostatic expansion valve system should hold a superheat of 8°F to 12°F at rated load |
| T15 | What is the maximum ambient temperature for rated capacity on the XC14? | `125°F` | **PASS** | PASS | text | p.5 | The XC14 must not be used for rated capacity above a 125°F ambient temperature |
| T16 | What is the specified control voltage for the YK series controls? | `24V` | **PASS** | PASS | text | p.3 | All YK series controls operate on 24V control power supplied from the factory control tran |
| T17 | What is the specified minimum duct static pressure the YK blower is rated for? | `0.25 in. w.c.` | **PASS** | PASS | text | p.4 | The YK blower is rated down to a minimum duct static pressure of 0.25 in. w.c. Below this  |
| T18 | What is the recommended cooling temperature differential on the YSC072 controller? | `4°F` | **PASS** | PASS | text | p.10 | Set the cooling temperature differential to 4°F for the standard YSC072 controller |
| T19 | What is the maximum allowable pressure drop across the liquid line filter drier during a pull-down? | `2 psi` | **PASS** | PASS | text | p.8 | During a full pull-down the pressure drop across the liquid line filter drier must not exc |
| T20 | What condensing temperature should be targeted on the XC14 when the outdoor temperature is 95°F? | `115°F` | **PASS** | PASS | text | p.6 | When the outdoor temperature is 95°F the target condensing temperature is 115°F. The readi |
| T21 | What is the specified torque for the YK thermostat setpoint screw? | `6 in. lb` | **PASS** | PASS | text | p.5 | Torque the setpoint screw on the YK thermostat to 6 in. lb after adjusting the heating and |


## 7. Unanswerability verification

No picture-only answer appears in the text corpus. All 15 are genuinely unanswerable from text alone.
