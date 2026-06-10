Query usata per generare i dati di tutte le persone:
```
PREFIX ocd:  <http://dati.camera.it/ocd/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX bio:  <http://purl.org/vocab/bio/0.1/>

SELECT DISTINCT
  ?persona
  ?nome
  ?cognome
  ?dataNascita
  ?dataMorte
  ?riferimento
  ?legislatura
WHERE {
  ?persona a foaf:Person .

  OPTIONAL { ?persona foaf:firstName ?nome . }
  OPTIONAL { ?persona foaf:surname ?cognome . }

  OPTIONAL {
    ?persona bio:Birth ?birth .
    ?birth bio:date ?dataNascita .
  }

  OPTIONAL {
    ?persona bio:Death ?death .
    ?death bio:date ?dataMorte .
  }

  OPTIONAL {
    {
      ?persona ocd:rif_mandatoSenato ?mandato .
      ?mandato ocd:rif_leg ?legislatura .
      BIND("senato" AS ?riferimento)
    }
    UNION
    {
      ?persona ocd:rif_mandatoCamera ?mandato .
      ?mandato ocd:rif_leg ?legislatura .
      BIND("camera" AS ?riferimento)
    }
    UNION
    {
      ?persona ocd:rif_membroGoverno ?membroGoverno .
      ?membroGoverno ocd:rif_leg ?legislatura .
      BIND("governo" AS ?riferimento)
    }
  }
}
LIMIT 10000
OFFSET 40000
```

Il valore di `OFFSET` va cambiato in base al set (al massimo si possono ottenere 10,000 risultati).
I file, salvati `set1.tsv`, `set2.tsv`, ecc. possono essere poi uniti con il comando:
```
cat set* | sort > persone.tsv
```

Questa è la query per la Consulta Nazionale:
```
PREFIX ocd:  <http://dati.camera.it/ocd/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX bio:  <http://purl.org/vocab/bio/0.1/>

SELECT DISTINCT ?persona ?nome ?cognome ?dataNascita ?dataMorte ?valoreConsulta
WHERE {
  {
    ?persona ocd:membroConsulta ?valoreConsulta .
    FILTER(LCASE(STR(?valoreConsulta)) = "true")
  }
  UNION
  {
    VALUES ?persona {
      <http://dati.camera.it/ocd/persona.rdf/pr12196>
    }
    BIND("true-aggiunto-manualmente" AS ?valoreConsulta)
  }

  OPTIONAL { ?persona foaf:firstName ?nome . }
  OPTIONAL { ?persona foaf:surname ?cognome . }

  OPTIONAL {
    ?persona bio:Birth ?birth .
    ?birth bio:date ?dataNascita .
  }

  OPTIONAL {
    ?persona bio:Death ?death .
    ?death bio:date ?dataMorte .
  }
}
ORDER BY ?cognome ?nome ?persona
```

Ottenere le legislature:
```
PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc:  <http://purl.org/dc/elements/1.1/>

SELECT DISTINCT ?legislatura ?dataInizio ?dataFine
WHERE {
  ?legislatura a ocd:legislatura ;
               dc:date ?date .

  BIND(STRBEFORE(STR(?date), "-") AS ?dataInizio)
  BIND(STRAFTER(STR(?date), "-") AS ?dataFine)
}
ORDER BY ?legislatura
```

Query per i senatori del Regno:
```
PREFIX ocd:  <http://dati.camera.it/ocd/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX bio:  <http://purl.org/vocab/bio/0.1/>
PREFIX dc:   <http://purl.org/dc/elements/1.1/>

SELECT DISTINCT
  ?persona
  ?nome
  ?cognome
  ?dataNascita
  ?dataMorte
  ?dataInizioMandato
  ?dataFineMandato
WHERE {
  ?persona a foaf:Person ;
           ocd:rif_mandatoSenato ?mandatoSenato .

  OPTIONAL { ?persona foaf:firstName ?nome . }
  OPTIONAL { ?persona foaf:surname ?cognome . }

  OPTIONAL {
    ?persona bio:Birth ?birth .
    ?birth bio:date ?dataNascita .
  }

  OPTIONAL {
    ?persona bio:Death ?death .
    ?death bio:date ?dataMorte .
  }

  ?mandatoSenato dc:date ?dateMandato .

  BIND(STRBEFORE(STR(?dateMandato), "-") AS ?dataInizioMandato)
  BIND(STRAFTER(STR(?dateMandato), "-") AS ?dataFineMandato)
}
ORDER BY ?cognome ?nome ?persona ?dataInizioMandato
```

