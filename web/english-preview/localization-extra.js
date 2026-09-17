// Templates added after an exhaustive scan of the published event and person records.
(() => {
const E=TerraEnglish,base=E.tr;
Object.assign(E.labels,{'податель разумения':'giver of understanding','податель гроз':'bringer of storms','страж мёртвых':'guardian of the dead','солнечный лик':'solar deity','мать урожая':'mother of the harvest','хранитель очага':'guardian of the hearth','ударить первыми':'strike first','умилостивить высшие силы':'appease higher powers','породниться и слиться':'form kinship ties and unite','терпеть и урезать доли':'endure and reduce rations','выжать из земли больше':'extract more from the land','торговать':'trade','переменить порядок':'change the social order','отнять у соседей':'seize resources from neighbors','держаться в стороне':'keep a distance','раскол':'separation','уступить недовольным':'make concessions to dissenters','отпустить с миром':'allow a peaceful departure','переустройство':'reorganization','освятить власть':'legitimize authority through religion','подавить силой':'suppress dissent by force','собрать власть в одних руках':'centralize power','истребить смутьянов':'kill dissenters','разделить власть':'share power','оставить как есть':'leave the situation unchanged','открыть всем':'share the knowledge with everyone','бросить затею':'abandon the project'});
E.tr=function(s){if(typeof s!=='string')return s;let m;
if((m=s.match(/^(.+?) встретил (.+?) копьём\.$/)))return `${m[1]} met ${m[2]} with armed hostility.`;
if((m=s.match(/^(.+?) разграблен и сожжён\.$/)))return `${m[1]} was looted and burned.`;
if((m=s.match(/^(.+?) и (.+?) завязали обмен\.$/)))return `${m[1]} and ${m[2]} established exchange.`;
if((m=s.match(/^(.+?) присоединил земли народа (.+?) к своей державе\.$/)))return `${m[1]} annexed the lands of ${m[2]}.`;
if((m=s.match(/^(.+?) из народа (.+?) (довёл до конца|утаил для своих|открыл всем) замысел: (.+?)\.?$/))){const action={'довёл до конца':'completed a project on','утаил для своих':'kept within the community a project on','открыл всем':'shared publicly a project on'}[m[3]];return `${m[1]} of ${m[2]} ${action} ${E.tr(m[4])}.`;}
if((m=s.match(/^(.+?) отступился от замысла: (.+?)\.?$/)))return `${m[1]} abandoned a project on ${E.tr(m[2])}.`;
if((m=s.match(/^(.+?) велел записать законы народа (.+?)\.$/)))return `${m[1]} ordered the laws of ${m[2]} to be written down.`;
if((m=s.match(/^(утаил для своих|открыл всем) замысел: (.+)$/)))return `${m[1]==='утаил для своих'?'Kept within the community':'Shared publicly'} a project on ${E.tr(m[2])}.`;
return base(s);
};
})();
