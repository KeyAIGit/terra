// English presentation only. Identifiers, dates and simulation quantities are preserved.
const TerraEnglish = (() => {
  const labels = {
    'палеолит':'Paleolithic','неолит':'Neolithic','бронза':'Bronze Age','античность':'Antiquity','средневековье':'Medieval',
    'раннее новое время':'Early modern','новое время':'Modern','индустриальная эпоха':'Industrial','современность':'Contemporary',
    'океан':'Ocean','лёд':'Ice','тундра':'Tundra','тайга':'Taiga','широколиственный лес':'Temperate forest','степь':'Steppe','средиземноморье':'Mediterranean','пустыня':'Desert','полупустыня':'Semiarid land','саванна':'Savanna','тропический лес':'Tropical forest','горы':'Mountains','болота':'Wetlands','озеро':'Lake',
    'охотники-собиратели':'hunter-gathering','оседлые собиратели':'settled foraging','мотыжное земледелие':'horticulture','скотоводы':'pastoralism','пашенное земледелие':'plough agriculture','ирригационное хозяйство':'irrigated agriculture',
    'община':'community','племя':'tribe','вождество бигменов':'big-man society','вождество':'chiefdom','город-государство':'city-state','царство':'kingdom','держава':'empire','республика':'republic','союз':'confederation',
    'стоянка':'camp','селение':'village','деревня':'village','городок':'town','город':'city','большой город':'large city','метрополия':'metropolis',
    'общинник':'commoner','старейшина':'elder','охотник':'hunter','земледелец':'farmer','знахарь':'healer','ремесленник':'artisan','жрец':'priest','воин':'warrior','торговец':'trader','писец':'scribe','вождь':'leader','смутьян':'dissenter',
    'любопытство':'curiosity','склонность к риску':'risk-taking','агрессия':'aggression','общительность':'sociability','конформизм':'conformity','амбиции':'ambition','терпение':'patience','эмпатия':'empathy','набожность':'piety','усердие':'diligence',
    '«там лучше, чем здесь»':'Life is better elsewhere','«чужие опасны»':'Outsiders are dangerous','«новое работает»':'New ideas can work','«своим можно верить»':'Our own people can be trusted','«власть законна»':'Authority is legitimate','«миром правят высшие силы»':'Higher powers govern the world','«еды не хватит»':'Food may run short',
    'алфавит':'alphabetic writing','амбар':'granaries','арка и свод':'arches and vaults','архив и школа':'archives and schools','астрономия':'astronomy','блок и полиспаст':'pulleys and tackle','бобовые в поле':'field legumes','боевая колесница':'war chariots','брожение':'fermentation','бумага':'paper','верховая езда':'horse riding','ветряная мельница':'windmills','водяная мельница':'watermills','возделывание':'crop cultivation','выплавка меди':'copper smelting','гидравлический раствор':'hydraulic mortar','горн':'furnaces','городская стена':'city walls','дань':'tribute','долблёный чёлн':'dugout canoes','долг и процент':'debt and interest','дороги':'roads','доспех':'armor','дощатая лодка':'plank boats','жречество':'organized priesthood','закалённая сталь':'hardened steel','землемерие':'land surveying','известь и штукатурка':'lime and plaster','календарь':'calendars','канал':'canals','канализация и водовод':'sewers and aqueducts','керамика':'pottery','килевое судно':'keeled ships','клубневое хозяйство':'tuber cultivation','колесо':'the wheel','культ предков':'ancestor worship','линзы':'lenses','лук и стрелы':'bows and arrows','мегалит':'megaliths','меха':'bellows','механические часы':'mechanical clocks','молочное хозяйство':'dairying','монета':'coinage','монументальное строительство':'monumental construction','мост':'bridges','мыло и щёлочь':'soap and alkali','мышьяковистая бронза':'arsenical bronze','навигация по звёздам':'stellar navigation','народное собрание':'popular assemblies','нравственное божество':'moralizing deities','одомашнивание растений':'plant domestication','оловянная бронза':'tin bronze','опытный метод':'experimental methods','орошение':'irrigation','осадное дело':'siegecraft','оседлость':'sedentary settlement','паровая машина':'steam engines','парус':'sails','перераспределение':'redistribution','печать':'printing','писаный закон':'written law','письменность':'writing','повозка':'wagons','позиционный счёт':'positional numerals','порох':'gunpowder','постоянная дружина':'standing armed retinues','право владения':'property rights','приручение стада':'herd domestication','простые механизмы':'simple machines','протописьмо':'proto-writing','рабство':'slavery','родовспоможение':'midwifery','рынок':'markets','садоводство и прививка':'orchards and grafting','самородная медь':'native copper working','самострел':'crossbows','севооборот и пар':'crop rotation and fallowing','собака':'dog domestication','соха':'ard ploughs','стекло':'glass','счётные фишки':'counting tokens','сыродутное железо':'bloomery iron','сырцовый и обожжённый кирпич':'mud and fired bricks','террасирование':'terracing','тягловый скот':'draft animals','тяжёлый плуг':'heavy ploughs','философия':'philosophy','хирургия и трепанация':'surgery and trepanation','хомут':'horse collars','цех и ремесленная каста':'guilds and craft castes','чиновничество':'bureaucracy','шерсть и руно':'wool production','шитая одежда':'sewn clothing',
    'огонь':'fire','каменные орудия':'stone tools','копьё':'spears','рыболовство':'fishing','сеть':'nets','плетение':'weaving','ткачество':'textile weaving',
    'довести замысел до конца':'complete the project','утаить для своих':'keep the knowledge within the community','потребовать дани':'demand tribute','увести народ прочь':'lead the people away','замысел':'project','встреча':'encounter','бедствие':'crisis','власть':'authority',
    'хозяин вод':'guardian of the waters','бог битвы':'deity of battle','хранитель урожая':'guardian of the harvest','бог плодородия':'deity of fertility','владыка неба':'ruler of the sky','покровитель ремесла':'patron of craftsmanship','дух предков':'ancestral spirit'
  };
  const modes={forager:'Hunter-gathering',complex_forager:'Settled foraging',horticulture:'Horticulture',pastoral:'Pastoralism',agrarian:'Plough agriculture',intensive:'Irrigated agriculture'};
  const forms={band:'Community',tribe:'Tribe',bigman:'Big-man society',chiefdom:'Chiefdom',citystate:'City-state',kingdom:'Kingdom',empire:'Empire',republic:'Republic',confederation:'Confederation'};
  const kinds={origin:'Origins',form:'Government',mode:'Livelihood',discovery:'Discovery',diffusion:'Knowledge exchange',loss:'Knowledge lost',city:'Settlement',build:'Construction',war:'Conflict',contact:'Encounter',decision:'Decision',fission:'Separation',merge:'Union',extinction:'Disappearance',epidemic:'Epidemic',rule:'Leadership',death:'Death',collapse:'Collapse',religion:'Belief'};
  const unresolved=new Set();
  const ru=/[А-Яа-яЁё]/;
  function tr(s){
    if(typeof s!=='string'||!ru.test(s))return s;
    if(labels[s]!==undefined)return labels[s];
    const clean=s.replace(/[.]$/,'');if(labels[clean]!==undefined)return labels[clean]+(s.endsWith('.')?'.':'');
    let m;
    if((m=s.match(/^(\d+) народов расселились по земле; всего людей около (.+)$/)))return `${m[1]} peoples settled across the world, with an aggregate population of approximately ${m[2]}.`;
    if((m=s.match(/^От народа (.+?) отделился (.+?) \((.+?) душ\)\.?$/)))return `${m[2]} separated from ${m[1]}, with a population of ${m[3]}.`;
    if((m=s.match(/^(.+?) обложен данью в пользу (.+?)\.$/)))return `${m[1]} became tributary to ${m[2]}.`;
    if((m=s.match(/^Мор прошёл по народу (.+?): погиб примерно каждый (\d+)-й\.$/)))return `An epidemic struck ${m[1]}; approximately one in ${m[2]} died.`;
    if((m=s.match(/^(.+?) из народа (.+?) впервые (?:сделал|додумался|измыслил|постиг): (.+?)\.?$/)))return `${m[1]} of ${m[2]} developed ${tr(m[3])}.`;
    if((m=s.match(/^впервые (?:сделал|додумался|измыслил|постиг): (.+)$/)))return `Developed ${tr(m[1])}.`;
    if((m=s.match(/^(.+?) перенял у народа (.+?): (.+?)\.?$/)))return `${m[1]} learned ${tr(m[3])} from ${m[2]}.`;
    if((m=s.match(/^(.+?) утратил умение: (.+?)\.?$/)))return `${m[1]} lost knowledge of ${tr(m[2])}.`;
    if((m=s.match(/^(.+?) переходит: (.+?) → (.+)$/)))return `${m[1]} shifted from ${tr(m[2])} to ${tr(m[3])}.`;
    if((m=s.match(/^Основан (.+?) — первое постоянное поселение народа (.+?)\.$/)))return `${m[1]} was founded as the first permanent settlement of ${m[2]}.`;
    if((m=s.match(/^(.+?) вырос: (.+?) → (.+?) \((.+?) жителей\)$/)))return `${m[1]} grew from ${tr(m[2])} to ${tr(m[3])}, with ${m[4]} inhabitants.`;
    if((m=s.match(/^(.+?) одолел (.+?), отняв (\d+) земель\.$/)))return `${m[1]} defeated ${m[2]} and took ${m[3]} territory cells.`;
    if((m=s.match(/^(.+?) одолел (.+?)\.$/)))return `${m[1]} defeated ${m[2]}.`;
    if((m=s.match(/^(.+?): (.+?) → (.+?) \((.+?) душ\)$/)))return `${m[1]} changed from ${tr(m[2])} to ${tr(m[3])}, with ${m[4]} people.`;
    if((m=s.match(/^Держава (.+?) обрушилась: из (.+?) душ осталось (.+?)\.$/)))return `${m[1]} collapsed; its population fell from ${m[2]} to ${m[3]}.`;
    if((m=s.match(/^(.+?) встал во главе народа (.+?)\.$/)))return `${m[1]} became leader of ${m[2]}.`;
    if((m=s.match(/^Народ (.+?) исчез\.$/)))return `${m[1]} disappeared from the simulation record.`;
    if((m=s.match(/^В городе (.+?) воздвигнуто святилище (.+?)\.$/)))return `A sanctuary of ${m[2]} was built in ${m[1]}.`;
    if((m=s.match(/^(.+?) увёл народ (.+?) с истощённой земли\.$/)))return `${m[1]} led ${m[2]} away from exhausted land.`;
    if((m=s.match(/^(.+?) переменил порядок в народе (.+?)\.$/)))return `${m[1]} changed the social order of ${m[2]}.`;
    if((m=s.match(/^(.+?) истребил смутьянов в народе (.+?)\.$/)))return `${m[1]} killed dissenters among ${m[2]}.`;
    if((m=s.match(/^Власть в народе (.+?) освящена именем (.+?)\.$/)))return `Authority among ${m[1]} was legitimized in the name of ${m[2]}.`;
    if((m=s.match(/^(.+?) принёс жертву, чтобы отвести беду от народа (.+?)\.$/)))return `${m[1]} made an offering to avert misfortune for ${m[2]}.`;
    if((m=s.match(/^(.+?) повёл народ (.+?) за чужим хлебом\.$/)))return `${m[1]} led ${m[2]} to seize food from others.`;
    if((m=s.match(/^(.+?) усмирил недовольных силой \((.+?)\)\.$/)))return `${m[1]} suppressed dissent by force in ${m[2]}.`;
    if((m=s.match(/^У народа (.+?) явился (.+?) — (.+?)\.$/)))return `${m[2]}, ${tr(m[3])}, entered the beliefs of ${m[1]}.`;
    if((m=s.match(/^В народе (.+?) (.+?) слились в (.+?)\.$/)))return `Among ${m[1]}, ${m[2]} merged into the deity ${m[3]}.`;
    if((m=s.match(/^на развилке «(.+?)» выбрал: (.+)$/)))return `At a ${tr(m[1])} juncture, chose to ${tr(m[2])}.`;
    if((m=s.match(/^довёл до конца замысел: (.+)$/)))return `Completed a project on ${tr(m[1])}.`;
    if((m=s.match(/^(.+?) народа (.+)$/))&&!ru.test(m[1]+m[2]))return `${m[1]} of ${m[2]}.`;
    let out=s;for(const [a,b] of Object.entries(labels).sort((a,b)=>b[0].length-a[0].length))out=out.split(a).join(b);
    if(!ru.test(out))return out;
    unresolved.add(s);return 'Historical record awaiting an English translation';
  }
  function deep(v){if(typeof v==='string')return tr(v);if(Array.isArray(v))return v.map(deep);if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,deep(x)]));return v;}
  const year=y=>y<0?`${Math.abs(y).toLocaleString('en-US')} BCE`:`${y.toLocaleString('en-US')} CE`;
  const number=n=>Math.round(Number(n)||0).toLocaleString('en-US');
  const short=n=>Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(Number(n)||0);
  return {tr,deep,labels,modes,forms,kinds,year,number,short,unresolved};
})();
