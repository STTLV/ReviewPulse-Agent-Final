"""Calcula subgrupos de IA responsable sobre Gold con el clasificador guardado, SIN red.

No altera corridas.csv, trazas ni umbrales. Salida: experiments/resultados/gold_subgrupos_responsable/.
Ejecutar desde la raiz del proyecto: python experiments/analizar_subgrupos_gold_responsable.py
"""
from __future__ import annotations
import csv, json, sys, warnings
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from reviewpulse import corpus
from reviewpulse.modelo import ClasificadorSentimiento
import joblib

def main():
    out=ROOT/'experiments/resultados/gold_subgrupos_responsable'
    with (ROOT/'data/gold/gold.csv').open(encoding='utf-8-sig',newline='') as f:
        gold=list(csv.DictReader(f))
    if len(gold)!=120: raise ValueError('Se necesitan 120 reseñas Gold.')
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        clf=joblib.load(ROOT/'data/modelo.joblib')
    preds=clf.predecir([r['texto'] for r in gold])
    flags=[]
    def instrumentado(texto,rng):
        typo=False
        if rng.random()<0.25: texto=texto.lower()
        if rng.random()<0.20: texto=corpus._quitar_tildes(texto)
        if rng.random()<0.10 and len(texto)>10:
            i=rng.randrange(1,len(texto)-2)
            texto=texto[:i]+texto[i+1]+texto[i]+texto[i+2:];typo=True
        if rng.random()<0.10: texto+=rng.choice([' 😊',' 👎','!!',' 🙄',' 👌'])
        flags.append(typo)
        return texto
    corpus._ruido=instrumentado
    reg=corpus.construir_corpus(120,2026,'evaluacion',0.10)
    if [x['texto'] for x in reg]!=[x['texto'] for x in gold]:
        raise ValueError('El generador no reproduce exactamente Gold; no se etiquetara el tipeo.')
    lens=[len(r['texto']) for r in gold]
    lc,lm=sorted(lens)[39],sorted(lens)[79]
    def grp_len(n): return 'corta' if n<=lc else ('media' if n<=lm else 'larga')
    detalle=[];grupos=defaultdict(list)
    for g,p,tipo,n in zip(gold,preds,flags,lens):
        cp=int(p.polaridad==g['polaridad']);ct=int(p.tema==g['tema'])
        row={'id':g['id'],'tema_gold':g['tema'],'polaridad_gold':g['polaridad'],
             'polaridad_predicha':p.polaridad,'confianza_polaridad':f'{p.conf_polaridad:.6f}',
             'tema_predicho':p.tema,'confianza_tema':f'{p.conf_tema:.6f}',
             'longitud_caracteres':n,'grupo_longitud':grp_len(n),
             'tipeo_permutacion_generador':int(tipo),'polaridad_correcta':cp,
             'tema_correcto':ct,'ambas_correctas':cp*ct}
        detalle.append(row)
        for dim,valor in [('tema',g['tema']),('tipeo','con_permutacion' if tipo else 'sin_permutacion'),('longitud',grp_len(n))]:
            grupos[dim,valor].append(row)
    tabla=[]
    for (dim,val),rec in sorted(grupos.items()):
        n=len(rec);cp=sum(r['polaridad_correcta'] for r in rec);ct=sum(r['tema_correcto'] for r in rec);ca=sum(r['ambas_correctas'] for r in rec)
        tabla.append({'dimension':dim,'valor':val,'n':n,'aciertos_polaridad':cp,'exactitud_polaridad':f'{cp/n:.6f}',
                      'aciertos_tema':ct,'exactitud_tema':f'{ct/n:.6f}',
                      'aciertos_combinados':ca,'exactitud_combinada':f'{ca/n:.6f}',
                      'alcance':'clasificador guardado sobre Gold; no es la tasa de éxito T13'})
    def escribir(nombre,datos):
        with (out/nombre).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(datos[0]),lineterminator='\n');w.writeheader();w.writerows(datos)
    out.mkdir(parents=True,exist_ok=True)
    escribir('predicciones_gold.csv',detalle)
    escribir('subgrupos_gold.csv',tabla)
    original=clf.predecir([gold[2]['texto']])[0]
    corregida=clf.predecir([gold[2]['texto'].replace('much omás','mucho más')])[0]
    import sklearn
    resumen={'fecha':'2026-11-26','n_gold':120,'n_tipeo_permutado':sum(flags),
             'longitud_regla':{'corta':f'<= {lc}','media':f'{lc+1}-{lm}','larga':f'> {lm}'},
             'totales':{'polaridad_correcta':sum(r['polaridad_correcta'] for r in detalle),
                        'tema_correcto':sum(r['tema_correcto'] for r in detalle),
                        'ambas_correctas':sum(r['ambas_correctas'] for r in detalle)},
             'L02':{'polaridad_gold':gold[2]['polaridad'],'polaridad_predicha':original.polaridad,
                    'confianza_polaridad':round(original.conf_polaridad,5),
                    'contrafactual_corregir_tipeo':{'polaridad':corregida.polaridad,'confianza_polaridad':round(corregida.conf_polaridad,5)}},
             'sklearn_entorno':sklearn.__version__,
             'advertencias_version':[str(x.message).split(' from version ')[-1][:100] for x in w if 'version' in str(x.message)],
             'nota':'Análisis de Gold con clasificador guardado, no evaluación de éxito ReAct/base. El Gold es sintético; no extraer causalidad.'}
    (out/'resumen_gold.json').write_text(json.dumps(resumen,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Escritos',len(detalle),'registros Gold; con permutacion',sum(flags),'model version',sklearn.__version__)
    print('Polaridad/tema/ambas:',resumen['totales'])
if __name__=='__main__':main()
