# MAHO Maschinenkonstanten – Philips 432/10
**Referenz:** Maschinenkonstanten-Dokumentation E3.2174xC / E3.2462xC  
**Datei:** `2020_12_11-2000.CM`  
**Änderungsdatum Dokumentation:** 22.01.1987

> **Hinweis zu Inkrementen:** Alle Positionsangaben in Inkrementen entsprechen bei Impulsvervielfachung ×4 und üblichem Encoder 0,001 mm pro Inkrement. Die Achsen X und Y sind jeweils in positiver Zählrichtung konfiguriert, Z ebenfalls positiv (aufwärts = positiv).

---

## 1. Hardware-Konfiguration

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC0 | Anzahl I/O-Karten | **1** | Eine I/O-Karte |
| MC1 | Anzahl Drive-Module | **4** | 4 Antriebsplatinen vorhanden |
| MC2 | NC-RAM Gesamtspeicher | **224 KByte** | Speichergröße des NC-RAMs |
| MC4 | Handbedienpult | **0** | Kein Handbedienpult |
| MC9 | Grafikmodul | **1** | 2-Ebenen-Modul |

---

## 2. Maschinen-Konfiguration

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC10 | Anzahl Achsen | **3** | 3 Linearachsen (X, Y, Z) |
| MC11 | Ebenenanwahl bei Netz-Ein | **0** | G17 (XY-Ebene) |
| MC14 | Messsystemtyp | **71** | Metrisch |
| MC27 | Anzahl Werkzeuge | **99** | Magazingröße 99 Plätze |
| MC39 | Verzögerung WZ-Magazin-Ausgänge | **0** | 0 × 15 ms = 0 ms |
| MC61 | Ausgabe M-Adresse | **5** | Dekodiert und BCD |
| MC63 | Ausgabe T-Adresse | **0** | Aus |

---

## 3. Software-Konfiguration CNC

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC80 | Demo-Modus | **0** | Aus |
| MC81 | Anzeigart Bildschirm | **0** | Restweg (dist-to-go) |
| MC82 | Anzahl Punktedefinitionen | **99** | |
| MC83 | Anzahl E-Parameter | **99** | |
| MC84 | Anzeige Programmnummern | **0** | Mit Text |
| MC85 | Anzahl Programme / Macros | **50** | |
| MC86 | Softkey lock/unlock | **1** | Aktiv |

---

## 4. Achsen-Konfiguration (Zuordnung)

> Die Zuordnung von logischer Achse zu MC-Block ist nicht sequenziell – Y und Z sind vertauscht:

| Logische Achse | Adresse | Funktion | MC-Block | Drive |
|----------------|---------|----------|----------|-------|
| 1. Achse | **X** (88) | Geschl. Lageregelkreis | MC200–249 | Platine 1 / Platz 1 |
| 2. Achse | **Y** (89) | Geschl. Lageregelkreis | MC300–349 | Platine 2 / Platz 1 |
| 3. Achse | **Z** (90) | Geschl. Lageregelkreis | MC250–299 | Platine 1 / Platz 2 |
| 4. Achse | **B** (66) | — (nicht aktiv) | MC350–399 | — |

---

## 5. Achs-Parameter im Detail

### 5.1 X-Achse (MC200–249)

| MC-Nr. | Parameter | Wert | Umgerechnet |
|--------|-----------|------|-------------|
| MC200 | Drive-Modul | 1 | Drive-Platine 1 / Platz 1 |
| MC202 | Zählrichtung | +1 | Positiv |
| MC203 | Impulsvervielfachung | 2 | × 4 |
| MC205 | Eilgang | 25000 | **2500 mm/min** |
| MC206 | Tippvorschub | 15000 | **1500 mm/min** |
| MC208 | Referenzpunktfahren | 10000 | **1000 mm/min** |
| MC209 | Einfahrpos. SW-Endschalter | 1000 | 1000 Inkremente |
| MC215 | Schleppabstand 1 bei 10 V | 2775 | 2775 Inkremente |
| MC216 | Knickpunkt | 2775 | 2775 Inkremente |
| MC217 | Schleppabstand 2 bei 10 V | 2775 | 2775 Inkremente |
| MC218 | Geführte Beschl./Verzög. | 2 | Doppelt |
| MC219 | Hochlaufzeit | 100 | **100 ms** |
| MC220 | Sollwertsprung | 0 | 0 mm/min |
| MC221 | In-Position Verzögerung | 5 | **75 ms** (5 × 15 ms) |
| MC222 | In-Position Fenster | 10 | 10 Inkremente |
| MC223 | Stillstandsüberwachung | 200 | 200 Inkremente |
| MC224 | Spielausgleich | 0 | Kein Spiel |
| MC230 | Anfahrrichtung Ref.-Punkt | −1 | **Negativ** |
| MC231 | Anfahrgeschwindigkeit | 10000 | **1000 mm/min** |
| MC232 | Schleichgang | 100 | **10 mm/min** |
| MC233 | Referenzpunktverschiebung | −400600 | −400.6 mm |
| MC234 | Gebietschalter Ref.-Punkt | 0 | Nicht aktiv |
| MC235 | SW-Endschalter + Richtung | +401100 | **+401.1 mm** |
| MC236 | SW-Endschalter − Richtung | +100 | +0.1 mm (Maschinennull) |
| MC237 | Wechselposition 1 (M68/M86) | −11500 | −11.5 mm |
| MC238 | Wechselposition 2 (M68) | 0 | 0 mm |
| MC240 | Festtaster Position | 0 | 0 |
| MC242 | Messtaster Kalibrierring | −1 | −1 Inkremente |

### 5.2 Y-Achse (MC300–349)

| MC-Nr. | Parameter | Wert | Umgerechnet |
|--------|-----------|------|-------------|
| MC300 | Drive-Modul | 3 | Drive-Platine 2 / Platz 1 |
| MC302 | Zählrichtung | +1 | Positiv |
| MC303 | Impulsvervielfachung | 2 | × 4 |
| MC305 | Eilgang | 25000 | **2500 mm/min** |
| MC306 | Tippvorschub | 15000 | **1500 mm/min** |
| MC308 | Referenzpunktfahren | 10000 | **1000 mm/min** |
| MC309 | Einfahrpos. SW-Endschalter | 1000 | 1000 Inkremente |
| MC315 | Schleppabstand 1 bei 10 V | 2775 | 2775 Inkremente |
| MC316 | Knickpunkt | 2775 | 2775 Inkremente |
| MC317 | Schleppabstand 2 bei 10 V | 2775 | 2775 Inkremente |
| MC318 | Geführte Beschl./Verzög. | 2 | Doppelt |
| MC319 | Hochlaufzeit | 100 | **100 ms** |
| MC320 | Sollwertsprung | 0 | 0 mm/min |
| MC321 | In-Position Verzögerung | 5 | **75 ms** |
| MC322 | In-Position Fenster | 10 | 10 Inkremente |
| MC323 | Stillstandsüberwachung | 200 | 200 Inkremente |
| MC324 | Spielausgleich | 0 | Kein Spiel |
| MC330 | Anfahrrichtung Ref.-Punkt | +1 | **Positiv** |
| MC331 | Anfahrgeschwindigkeit | 10000 | **1000 mm/min** |
| MC332 | Schleichgang | 0 | — |
| MC333 | Referenzpunktverschiebung | +249500 | +249.5 mm |
| MC334 | Gebietschalter Ref.-Punkt | 0 | Nicht aktiv |
| MC335 | SW-Endschalter + Richtung | +1500 | +1.5 mm |
| MC336 | SW-Endschalter − Richtung | −250000 | **−250.0 mm** |
| MC337 | Wechselposition 1 (M68/M86) | −346000 | −346.0 mm |
| MC338 | Wechselposition 2 (M68) | 0 | 0 mm |
| MC340 | Festtaster Position | 0 | 0 |
| MC342 | Messtaster Kalibrierring | −1 | −1 Inkremente |

### 5.3 Z-Achse (MC250–299)

| MC-Nr. | Parameter | Wert | Umgerechnet |
|--------|-----------|------|-------------|
| MC250 | Drive-Modul | 2 | Drive-Platine 1 / Platz 2 |
| MC252 | Zählrichtung | +1 | Positiv (aufwärts = positiv) |
| MC253 | Impulsvervielfachung | 2 | × 4 |
| MC255 | Eilgang | 25000 | **2500 mm/min** |
| MC256 | Tippvorschub | 15000 | **1500 mm/min** |
| MC258 | Referenzpunktfahren | 10000 | **1000 mm/min** |
| MC259 | Einfahrpos. SW-Endschalter | 1000 | 1000 Inkremente |
| MC265 | Schleppabstand 1 bei 10 V | 2775 | 2775 Inkremente |
| MC266 | Knickpunkt | 2775 | 2775 Inkremente |
| MC267 | Schleppabstand 2 bei 10 V | 2775 | 2775 Inkremente |
| MC268 | Geführte Beschl./Verzög. | 2 | Doppelt |
| MC269 | Hochlaufzeit | 100 | **100 ms** |
| MC270 | Sollwertsprung | 0 | 0 mm/min |
| MC271 | In-Position Verzögerung | 5 | **75 ms** |
| MC272 | In-Position Fenster | 10 | 10 Inkremente |
| MC273 | Stillstandsüberwachung | 200 | 200 Inkremente |
| MC274 | Spielausgleich | 0 | Kein Spiel |
| MC280 | Anfahrrichtung Ref.-Punkt | +1 | **Positiv** (Spindel fährt hoch) |
| MC281 | Anfahrgeschwindigkeit | 10000 | **1000 mm/min** |
| MC282 | Schleichgang | 0 | — |
| MC283 | Referenzpunktverschiebung | +322500 | +322.5 mm |
| MC284 | Gebietschalter Ref.-Punkt | 0 | Nicht aktiv |
| MC285 | SW-Endschalter + Richtung | −100 | −0.1 mm (oberer Anschlag) |
| MC286 | SW-Endschalter − Richtung | −323000 | **−323.0 mm** (Verfahrweg ~323 mm) |
| MC287 | Wechselposition 1 (M68/M86) | +173000 | +173.0 mm (WZ-Wechselhöhe) |
| MC288 | Wechselposition 2 (M68) | 0 | 0 mm |
| MC290 | Festtaster Position | 0 | 0 |
| MC292 | Messtaster Kalibrierring | −1 | −1 Inkremente |

### 5.4 B-Achse (MC350–399) – nicht aktiv

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC350 | Drive-Modul | 0 | **Nicht aktiv** |
| MC352 | Zählrichtung | +1 | Positiv (Default) |
| MC353 | Impulsvervielfachung | 0 | 1:1 |
| MC383 | Referenzpunktverschiebung | −1 | — |
| MC384 | Gebietschalter Ref.-Punkt | 0 | Nicht aktiv |
| MC385 | SW-Endschalter + Richtung | −1 | — |
| MC386 | SW-Endschalter − Richtung | 0 | — |

---

## 6. Spindel-Parameter

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC579 | Fraesspindeldrehzahlreihe (10-stufig) | **5** | Drehzahlbereich **80–4000 U/min** |
| MC590 | Fraesspindeltakt Pausenzeit | 8 | **400 ms** (8 × 50 ms) |
| MC591 | Fraesspindeltakt Impulszeit | 10 | **500 ms** (10 × 50 ms) |

---

## 7. Allgemeine Maschinenkonstanten

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC705 | Dezimalpunkt Weginformation | 3 | 0,001 mm Auflösung |
| MC706 | Dezimalpunkt Vorschubwerte | 3 | 0,001 mm/min Auflösung |
| MC707 | Zoll/Metrisch bei Netz-Ein | 71 | **Metrisch** |
| MC710 | Tangential-Übergang Grenzwert | 10 | 10 Inkremente → Kreis oder Gerade |
| MC711 | Rundungswinkel G41/G42 | 44 | **44°** |
| MC712 | Zielpunktfenster Kreisprog. (IJK) | 10 | 10 Inkremente |
| MC713 | Schruppen | 0 | Aus |
| MC714 | Vergrößerung/Verkleinerung | 2 | Faktor mit Werkzeugachse |
| MC715 | Dezimalpunkt Skalierungsfaktor | 6 | |
| MC720 | Werkzeugüberlappung Taschenfräsen | 83 | 83 × E |
| MC723 | Abstand Lochgrund für G84 | 5000 | 5000 Inkremente = 5 mm |
| MC724 | Umkehrzeit Links/Rechtslauf G84 | 0 | 0 × 15 ms |
| MC731 | Eingänge Open Loop | 0 | Nicht aktiviert |
| MC740 | Max. Vorschubgeschwindigkeit | 15000 | **1500 mm/min** |
| MC741 | Vorschub Testbetrieb | 10000 | **1000 mm/min** |
| MC745 | Vorschubbeeinflussung max. | 150 | **150 %** |
| MC746 | Vorschubbeeinflussung min. | 0 | **0 %** |

---

## 8. Serielle Datenkommunikation

| MC-Nr. | Parameter | Wert | Bedeutung |
|--------|-----------|------|-----------|
| MC770 | Ser. Daten-E/A Modus | 0 | Local V24, kein V11 |
| MC771 | Ausgabecode (data I/O) | 1 | **ISO** |
| MC772 | Autom. Codeerkennung | 2 | Nicht aktiv, XON/XOFF |
| MC773 | Nachgesendete Zeichen nach Stop | 30 | 30 Zeichen |
| MC775 | V24 Stopbits | 0 | **1 Stopbit** |
| MC776 | V24 Baudrate auslesen | 4800 | **4800 Baud** |
| MC777 | V24 Baudrate einlesen | 4800 | **4800 Baud** |
| MC785 | V11 Stopbits | 1 | **2 Stopbits** |
| MC786 | V11 Baudrate | 4800 | **4800 Baud** |
| MC796 | Summennummern-Überprüfung | 0 | Aus |

---

## 9. Zusammenfassung: Verfahrwege und Geschwindigkeiten

| Achse | Verfahrweg (SW-Grenzen) | Eilgang | Ref.-Richtung | Ref.-Verschiebung |
|-------|------------------------|---------|---------------|-------------------|
| X | +0.1 mm … +401.1 mm (~401 mm) | 2500 mm/min | Negativ | −400.6 mm |
| Y | −250.0 mm … +1.5 mm (~250 mm) | 2500 mm/min | Positiv | +249.5 mm |
| Z | −323.0 mm … −0.1 mm (~323 mm) | 2500 mm/min | Positiv (aufwärts) | +322.5 mm |
| B | — (nicht aktiv) | — | — | — |

**Alle Achsen: Impulsvervielfachung × 4, In-Position Fenster 10 Inkremente, Schleppabstand 2775 Inkremente bei 10 V, Hochlaufzeit 100 ms (doppelt geführte Beschleunigung)**

---

## 10. Hinweise für LinuxCNC INI / HAL

| Parameter | Relevanz für LinuxCNC |
|-----------|----------------------|
| Eilgang (MC205/255/305) | `MAX_VELOCITY` in der `[AXIS_x]`-Sektion |
| Tippvorschub (MC206/256/306) | `DEFAULT_VELOCITY` |
| Max. Vorschub (MC740) | globales `MAX_LINEAR_VELOCITY` |
| In-Position Fenster (MC222/272/322) | `FERROR` / `MIN_FERROR` |
| Stillstandsfenster (MC223/273/323) | `FERROR` (Grobfehler) |
| Spielausgleich (MC224/274/324) | `BACKLASH` (alle = 0) |
| SW-Endschalter (MC235/236 etc.) | `MIN_LIMIT` / `MAX_LIMIT` |
| Ref.-Verschiebung (MC233/283/333) | Encoder-Offset bei Homing |
| Ref.-Richtung (MC230/280/330) | `HOME_SEARCH_VEL` (Vorzeichen) |
| Anfahrgeschw. (MC231/281/331) | `HOME_SEARCH_VEL` |
| Schleichgang (MC232/282/332) | `HOME_LATCH_VEL` |
| V24 Baudrate (MC776/777) | Serielle Schnittstelle für DNC |
| Spindeldrehzahl max. (MC579 → 4000) | `MAX_FORWARD_VELOCITY` (Spindel) |
