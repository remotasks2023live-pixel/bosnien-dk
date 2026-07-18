# Sådan sætter du bosnien.dk op til automatisk opdatering

Du skal kun igennem dette **én gang**. Bagefter kører siden helt af sig selv –
den henter nye artikler om Bosnien-Hercegovina (sport, politik, turisme,
rejser, folk/kultur og bosnisk-danske nyheder) flere gange dagligt, uden du
skal røre noget.

Alle overskrifter oversættes automatisk til dansk, uanset hvilket sprog
kilden er skrevet på (bosnisk, engelsk osv.). Hold musen over en overskrift
på siden for at se den oprindelige, uoversatte titel.

Sæt ca. 20-30 minutter af.

---

## Trin 1: Opret en GitHub-konto
1. Gå til https://github.com/join
2. Opret en gratis konto (email + adgangskode).

## Trin 2: Opret et nyt "repository" (projektmappe)
1. Log ind på GitHub, klik **+** øverst til højre → **New repository**.
2. Navn: `bosnien-dk` (eller hvad du vil).
3. Vælg **Public**.
4. Klik **Create repository**.

## Trin 3: Upload filerne
1. På den nye repository-side: klik **uploading an existing file** (eller
   "Add file" → "Upload files").
2. Træk hele indholdet af den mappe, jeg har leveret, ind i browservinduet
   (alle filer og mapper: `fetch_news.py`, `requirements.txt`, `docs/`,
   `.github/`).
   - **Vigtigt:** Du skal beholde mappestrukturen. Hvis GitHub kun lader dig
     trække filer enkeltvis, kan du i stedet bruge "GitHub Desktop"-appen
     (https://desktop.github.com) og trække hele mappen ind der – den er
     lettere til mapper med undermapper.
3. Skriv en commit-besked, fx "Første opsætning", og klik **Commit changes**.

## Trin 4: Slå GitHub Pages til
1. Gå til repositoryets **Settings** → **Pages** (i venstre menu).
2. Under "Build and deployment" → **Source**: vælg **Deploy from a branch**.
3. Under **Branch**: vælg `main` og mappen `/docs`. Klik **Save**.
4. Under **Custom domain**: skriv `bosnien.dk` og klik **Save**.
   (Filen `docs/CNAME`, som allerede ligger i uploadet, gør at GitHub husker
   dette automatisk – men det er godt at bekræfte det her også.)
5. Sæt gerne flueben i **Enforce HTTPS** (kan tage lidt tid før den kan
   vælges – kom tilbage til det efter Trin 5).

## Trin 5: Peg dit domæne mod GitHub Pages
Log ind hos den, du har registreret bosnien.dk igennem (fx simply.com,
DanDomain, GratisDNS, one.com) og gå til DNS-indstillinger for domænet.

Tilføj disse **A-records** for `@` (roden af domænet, altså selve bosnien.dk):

```
185.199.108.153
185.199.109.153
185.199.110.153
185.199.111.153
```

Og en **CNAME-record** for `www`, der peger på:

```
<dit-github-brugernavn>.github.io
```

(Erstat `<dit-github-brugernavn>` med dit faktiske GitHub-brugernavn.)

DNS-ændringer kan tage fra få minutter til nogle timer om at slå igennem.

## Trin 6: Test den automatiske opdatering
1. Gå til fanen **Actions** i dit repository på GitHub.
2. Du vil se en workflow der hedder **"Opdater bosnien.dk"**.
3. Klik ind på den, klik **Run workflow** → **Run workflow** for at teste den
   med det samme (i stedet for at vente på den planlagte kørsel).
4. Efter ca. 1 minut, tjek https://bosnien.dk – siden bør nu vise rigtige
   nyheder i stedet for "klargøres"-beskeden.

Herefter kører den automatisk hver 6. time uden du behøver gøre noget som
helst.

---

## Hvis du vil justere noget senere (valgfrit)
Alt dette er valgfrit – siden virker fint som den er:

- **Hvor tit den opdaterer:** åbn `.github/workflows/update-site.yml` og
  ændr linjen `cron: "0 */6 * * *"` (fx til `"0 6 * * *"` for én gang
  dagligt kl. 06 UTC).
- **Hvilke kilder den bruger:** åbn `fetch_news.py` og se afsnittet
  `CATEGORIES` øverst – her kan du tilføje eller fjerne søgninger/RSS-links.
- **Design/farver:** i `fetch_news.py`, i variablen `PAGE_TEMPLATE`, under
  `<style>`.

## Fejlfinding
- **Siden viser 404:** Vent lidt længere på DNS, eller dobbelttjek
  A-records i Trin 5.
- **"Opdater bosnien.dk" fejler i Actions-fanen:** Klik ind på den fejlede
  kørsel og læs fejlbeskeden – oftest er det en midlertidig fejl hos en af
  nyhedskilderne, og den retter sig selv ved næste automatiske kørsel.
- **Siden opdaterer sig ikke:** Tjek under Actions at workflowet rent
  faktisk har kørt for nylig (grønt flueben = success).
- **Nogle overskrifter er ikke oversat (står stadig på bosnisk/engelsk):**
  Oversættelsestjenesten kan af og til være midlertidigt utilgængelig eller
  rate-begrænset. Scriptet falder da automatisk tilbage til originalteksten
  i stedet for at fejle helt – det retter sig selv ved næste kørsel.
