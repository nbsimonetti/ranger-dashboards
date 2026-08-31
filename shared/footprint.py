"""
Ranger Dashboards - shared refresh utilities.

Canonical footprint = ALL 254 Texas counties (name -> 5-digit state+county FIPS),
generated from the 2024 Census Gazetteer, plus each county's centroid in
COUNTY_GEO for maps. HTTP helpers with retry, and a marker-based data-injection
helper so each refresh script can rewrite its self-contained dashboard HTML in
place. Stdlib only, so it runs cleanly inside GitHub Actions.
"""
import json
import time
import re
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

USER_AGENT = "ranger-dashboards/1.0 (+https://nbsimonetti.github.io/ranger-dashboards)"

FOOTPRINT = {
    "Anderson": "48001", "Andrews": "48003", "Angelina": "48005", "Aransas": "48007",
    "Archer": "48009", "Armstrong": "48011", "Atascosa": "48013", "Austin": "48015",
    "Bailey": "48017", "Bandera": "48019", "Bastrop": "48021", "Baylor": "48023",
    "Bee": "48025", "Bell": "48027", "Bexar": "48029", "Blanco": "48031",
    "Borden": "48033", "Bosque": "48035", "Bowie": "48037", "Brazoria": "48039",
    "Brazos": "48041", "Brewster": "48043", "Briscoe": "48045", "Brooks": "48047",
    "Brown": "48049", "Burleson": "48051", "Burnet": "48053", "Caldwell": "48055",
    "Calhoun": "48057", "Callahan": "48059", "Cameron": "48061", "Camp": "48063",
    "Carson": "48065", "Cass": "48067", "Castro": "48069", "Chambers": "48071",
    "Cherokee": "48073", "Childress": "48075", "Clay": "48077", "Cochran": "48079",
    "Coke": "48081", "Coleman": "48083", "Collin": "48085", "Collingsworth": "48087",
    "Colorado": "48089", "Comal": "48091", "Comanche": "48093", "Concho": "48095",
    "Cooke": "48097", "Coryell": "48099", "Cottle": "48101", "Crane": "48103",
    "Crockett": "48105", "Crosby": "48107", "Culberson": "48109", "Dallam": "48111",
    "Dallas": "48113", "Dawson": "48115", "DeWitt": "48123", "Deaf Smith": "48117",
    "Delta": "48119", "Denton": "48121", "Dickens": "48125", "Dimmit": "48127",
    "Donley": "48129", "Duval": "48131", "Eastland": "48133", "Ector": "48135",
    "Edwards": "48137", "El Paso": "48141", "Ellis": "48139", "Erath": "48143",
    "Falls": "48145", "Fannin": "48147", "Fayette": "48149", "Fisher": "48151",
    "Floyd": "48153", "Foard": "48155", "Fort Bend": "48157", "Franklin": "48159",
    "Freestone": "48161", "Frio": "48163", "Gaines": "48165", "Galveston": "48167",
    "Garza": "48169", "Gillespie": "48171", "Glasscock": "48173", "Goliad": "48175",
    "Gonzales": "48177", "Gray": "48179", "Grayson": "48181", "Gregg": "48183",
    "Grimes": "48185", "Guadalupe": "48187", "Hale": "48189", "Hall": "48191",
    "Hamilton": "48193", "Hansford": "48195", "Hardeman": "48197", "Hardin": "48199",
    "Harris": "48201", "Harrison": "48203", "Hartley": "48205", "Haskell": "48207",
    "Hays": "48209", "Hemphill": "48211", "Henderson": "48213", "Hidalgo": "48215",
    "Hill": "48217", "Hockley": "48219", "Hood": "48221", "Hopkins": "48223",
    "Houston": "48225", "Howard": "48227", "Hudspeth": "48229", "Hunt": "48231",
    "Hutchinson": "48233", "Irion": "48235", "Jack": "48237", "Jackson": "48239",
    "Jasper": "48241", "Jeff Davis": "48243", "Jefferson": "48245", "Jim Hogg": "48247",
    "Jim Wells": "48249", "Johnson": "48251", "Jones": "48253", "Karnes": "48255",
    "Kaufman": "48257", "Kendall": "48259", "Kenedy": "48261", "Kent": "48263",
    "Kerr": "48265", "Kimble": "48267", "King": "48269", "Kinney": "48271",
    "Kleberg": "48273", "Knox": "48275", "La Salle": "48283", "Lamar": "48277",
    "Lamb": "48279", "Lampasas": "48281", "Lavaca": "48285", "Lee": "48287",
    "Leon": "48289", "Liberty": "48291", "Limestone": "48293", "Lipscomb": "48295",
    "Live Oak": "48297", "Llano": "48299", "Loving": "48301", "Lubbock": "48303",
    "Lynn": "48305", "Madison": "48313", "Marion": "48315", "Martin": "48317",
    "Mason": "48319", "Matagorda": "48321", "Maverick": "48323", "McCulloch": "48307",
    "McLennan": "48309", "McMullen": "48311", "Medina": "48325", "Menard": "48327",
    "Midland": "48329", "Milam": "48331", "Mills": "48333", "Mitchell": "48335",
    "Montague": "48337", "Montgomery": "48339", "Moore": "48341", "Morris": "48343",
    "Motley": "48345", "Nacogdoches": "48347", "Navarro": "48349", "Newton": "48351",
    "Nolan": "48353", "Nueces": "48355", "Ochiltree": "48357", "Oldham": "48359",
    "Orange": "48361", "Palo Pinto": "48363", "Panola": "48365", "Parker": "48367",
    "Parmer": "48369", "Pecos": "48371", "Polk": "48373", "Potter": "48375",
    "Presidio": "48377", "Rains": "48379", "Randall": "48381", "Reagan": "48383",
    "Real": "48385", "Red River": "48387", "Reeves": "48389", "Refugio": "48391",
    "Roberts": "48393", "Robertson": "48395", "Rockwall": "48397", "Runnels": "48399",
    "Rusk": "48401", "Sabine": "48403", "San Augustine": "48405", "San Jacinto": "48407",
    "San Patricio": "48409", "San Saba": "48411", "Schleicher": "48413", "Scurry": "48415",
    "Shackelford": "48417", "Shelby": "48419", "Sherman": "48421", "Smith": "48423",
    "Somervell": "48425", "Starr": "48427", "Stephens": "48429", "Sterling": "48431",
    "Stonewall": "48433", "Sutton": "48435", "Swisher": "48437", "Tarrant": "48439",
    "Taylor": "48441", "Terrell": "48443", "Terry": "48445", "Throckmorton": "48447",
    "Titus": "48449", "Tom Green": "48451", "Travis": "48453", "Trinity": "48455",
    "Tyler": "48457", "Upshur": "48459", "Upton": "48461", "Uvalde": "48463",
    "Val Verde": "48465", "Van Zandt": "48467", "Victoria": "48469", "Walker": "48471",
    "Waller": "48473", "Ward": "48475", "Washington": "48477", "Webb": "48479",
    "Wharton": "48481", "Wheeler": "48483", "Wichita": "48485", "Wilbarger": "48487",
    "Willacy": "48489", "Williamson": "48491", "Wilson": "48493", "Winkler": "48495",
    "Wise": "48497", "Wood": "48499", "Yoakum": "48501", "Young": "48503",
    "Zapata": "48505", "Zavala": "48507",
}

# fips -> (county name, centroid lat, centroid lng); 2024 Census Gazetteer
COUNTY_GEO = {
    "48001": ("Anderson", 31.8413, -95.6617), "48003": ("Andrews", 32.3123, -102.6402),
    "48005": ("Angelina", 31.2519, -94.6111), "48007": ("Aransas", 28.1226, -96.9675),
    "48009": ("Archer", 33.6163, -98.6873), "48011": ("Armstrong", 34.9642, -101.3566),
    "48013": ("Atascosa", 28.8915, -98.5354), "48015": ("Austin", 29.8919, -96.2702),
    "48017": ("Bailey", 34.0675, -102.8303), "48019": ("Bandera", 29.7564, -99.2483),
    "48021": ("Bastrop", 30.1008, -97.3106), "48023": ("Baylor", 33.6188, -99.2082),
    "48025": ("Bee", 28.4161, -97.7426), "48027": ("Bell", 31.0427, -97.4813),
    "48029": ("Bexar", 29.4487, -98.5201), "48031": ("Blanco", 30.2662, -98.3993),
    "48033": ("Borden", 32.7386, -101.4392), "48035": ("Bosque", 31.9008, -97.6376),
    "48037": ("Bowie", 33.4461, -94.4224), "48039": ("Brazoria", 29.1678, -95.4346),
    "48041": ("Brazos", 30.6567, -96.3024), "48043": ("Brewster", 29.8090, -103.2525),
    "48045": ("Briscoe", 34.5252, -101.2059), "48047": ("Brooks", 27.0350, -98.2153),
    "48049": ("Brown", 31.7641, -98.9985), "48051": ("Burleson", 30.4935, -96.6221),
    "48053": ("Burnet", 30.7896, -98.2012), "48055": ("Caldwell", 29.8324, -97.6281),
    "48057": ("Calhoun", 28.4417, -96.5796), "48059": ("Callahan", 32.2931, -99.3722),
    "48061": ("Cameron", 26.1029, -97.4790), "48063": ("Camp", 32.9746, -94.9791),
    "48065": ("Carson", 35.4055, -101.3554), "48067": ("Cass", 33.0837, -94.3576),
    "48069": ("Castro", 34.5336, -102.2588), "48071": ("Chambers", 29.6964, -94.6694),
    "48073": ("Cherokee", 31.8439, -95.1563), "48075": ("Childress", 34.5246, -100.2082),
    "48077": ("Clay", 33.7859, -98.2129), "48079": ("Cochran", 33.6084, -102.8304),
    "48081": ("Coke", 31.8771, -100.6352), "48083": ("Coleman", 31.9142, -99.3466),
    "48085": ("Collin", 33.1945, -96.5794), "48087": ("Collingsworth", 34.9634, -100.2721),
    "48089": ("Colorado", 29.5963, -96.5089), "48091": ("Comal", 29.8124, -98.2581),
    "48093": ("Comanche", 31.9516, -98.5496), "48095": ("Concho", 31.3189, -99.8636),
    "48097": ("Cooke", 33.6392, -97.2103), "48099": ("Coryell", 31.3912, -97.7980),
    "48101": ("Cottle", 34.0919, -100.2764), "48103": ("Crane", 31.4228, -102.4878),
    "48105": ("Crockett", 30.7175, -101.4042), "48107": ("Crosby", 33.6091, -101.2987),
    "48109": ("Culberson", 31.4459, -104.5269), "48111": ("Dallam", 36.2864, -102.5940),
    "48113": ("Dallas", 32.7670, -96.7784), "48115": ("Dawson", 32.7425, -101.9488),
    "48117": ("Deaf Smith", 34.9408, -102.6076), "48119": ("Delta", 33.3859, -95.6733),
    "48121": ("Denton", 33.2051, -97.1211), "48123": ("DeWitt", 29.0823, -97.3617),
    "48125": ("Dickens", 33.6154, -100.7876), "48127": ("Dimmit", 28.4236, -99.7659),
    "48129": ("Donley", 34.9550, -100.8158), "48131": ("Duval", 27.6811, -98.4974),
    "48133": ("Eastland", 32.3246, -98.8366), "48135": ("Ector", 31.8653, -102.5425),
    "48137": ("Edwards", 29.9859, -100.3074), "48139": ("Ellis", 32.3469, -96.7969),
    "48141": ("El Paso", 31.7665, -106.2415), "48143": ("Erath", 32.2367, -98.2205),
    "48145": ("Falls", 31.2519, -96.9341), "48147": ("Fannin", 33.5912, -96.1050),
    "48149": ("Fayette", 29.8779, -96.9212), "48151": ("Fisher", 32.7405, -100.4031),
    "48153": ("Floyd", 34.0737, -101.3033), "48155": ("Foard", 33.9633, -99.8168),
    "48157": ("Fort Bend", 29.5266, -95.7710), "48159": ("Franklin", 33.1758, -95.2191),
    "48161": ("Freestone", 31.7017, -96.1450), "48163": ("Frio", 28.8694, -99.1090),
    "48165": ("Gaines", 32.7439, -102.6316), "48167": ("Galveston", 29.2339, -94.8882),
    "48169": ("Garza", 33.1838, -101.3011), "48171": ("Gillespie", 30.3251, -98.9419),
    "48173": ("Glasscock", 31.8680, -101.5215), "48175": ("Goliad", 28.6607, -97.4304),
    "48177": ("Gonzales", 29.4619, -97.4919), "48179": ("Gray", 35.4025, -100.8124),
    "48181": ("Grayson", 33.6245, -96.6758), "48183": ("Gregg", 32.4864, -94.8163),
    "48185": ("Grimes", 30.5432, -95.9881), "48187": ("Guadalupe", 29.5827, -97.9490),
    "48189": ("Hale", 34.0684, -101.8229), "48191": ("Hall", 34.4532, -100.5763),
    "48193": ("Hamilton", 31.7073, -98.1118), "48195": ("Hansford", 36.2728, -101.3569),
    "48197": ("Hardeman", 34.2899, -99.7457), "48199": ("Hardin", 30.3296, -94.3932),
    "48201": ("Harris", 29.8573, -95.3930), "48203": ("Harrison", 32.5480, -94.3744),
    "48205": ("Hartley", 35.8402, -102.6100), "48207": ("Haskell", 33.1760, -99.7308),
    "48209": ("Hays", 30.0612, -98.0293), "48211": ("Hemphill", 35.8160, -100.2792),
    "48213": ("Henderson", 32.2116, -95.8534), "48215": ("Hidalgo", 26.3964, -98.1810),
    "48217": ("Hill", 31.9826, -97.1306), "48219": ("Hockley", 33.6059, -102.3434),
    "48221": ("Hood", 32.4301, -97.8317), "48223": ("Hopkins", 33.1490, -95.5654),
    "48225": ("Houston", 31.3230, -95.4216), "48227": ("Howard", 32.3034, -101.4387),
    "48229": ("Hudspeth", 31.4509, -105.3775), "48231": ("Hunt", 33.1233, -96.0842),
    "48233": ("Hutchinson", 35.8370, -101.3627), "48235": ("Irion", 31.3034, -100.9813),
    "48237": ("Jack", 33.2322, -98.1712), "48239": ("Jackson", 28.9598, -96.5891),
    "48241": ("Jasper", 30.7529, -94.0223), "48243": ("Jeff Davis", 30.6254, -104.1919),
    "48245": ("Jefferson", 29.8540, -94.1493), "48247": ("Jim Hogg", 27.0532, -98.7476),
    "48249": ("Jim Wells", 27.7335, -98.0908), "48251": ("Johnson", 32.3797, -97.3649),
    "48253": ("Jones", 32.7437, -99.8744), "48255": ("Karnes", 28.9090, -97.8522),
    "48257": ("Kaufman", 32.5989, -96.2884), "48259": ("Kendall", 29.9435, -98.7093),
    "48261": ("Kenedy", 26.8902, -97.5911), "48263": ("Kent", 33.1848, -100.7697),
    "48265": ("Kerr", 30.0600, -99.3533), "48267": ("Kimble", 30.4795, -99.7464),
    "48269": ("King", 33.6143, -100.2453), "48271": ("Kinney", 29.3471, -100.4177),
    "48273": ("Kleberg", 27.4387, -97.6606), "48275": ("Knox", 33.6119, -99.7304),
    "48277": ("Lamar", 33.6673, -95.5703), "48279": ("Lamb", 34.0689, -102.3480),
    "48281": ("Lampasas", 31.1967, -98.2409), "48283": ("La Salle", 28.3511, -99.0968),
    "48285": ("Lavaca", 29.3826, -96.9236), "48287": ("Lee", 30.3215, -96.9768),
    "48289": ("Leon", 31.3005, -95.9956), "48291": ("Liberty", 30.1585, -94.8441),
    "48293": ("Limestone", 31.5475, -96.5936), "48295": ("Lipscomb", 36.2802, -100.2727),
    "48297": ("Live Oak", 28.3515, -98.1270), "48299": ("Llano", 30.7076, -98.6847),
    "48301": ("Loving", 31.8449, -103.5612), "48303": ("Lubbock", 33.6115, -101.8199),
    "48305": ("Lynn", 33.1784, -101.8185), "48307": ("McCulloch", 31.2055, -99.3599),
    "48309": ("McLennan", 31.5496, -97.2015), "48311": ("McMullen", 28.3849, -98.5789),
    "48313": ("Madison", 30.9669, -95.9304), "48315": ("Marion", 32.7982, -94.3569),
    "48317": ("Martin", 32.3098, -101.9618), "48319": ("Mason", 30.7039, -99.2373),
    "48321": ("Matagorda", 28.7748, -96.0015), "48323": ("Maverick", 28.7298, -100.3167),
    "48325": ("Medina", 29.3537, -99.1111), "48327": ("Menard", 30.8853, -99.8589),
    "48329": ("Midland", 31.8143, -102.0025), "48331": ("Milam", 30.7912, -96.9844),
    "48333": ("Mills", 31.4949, -98.5946), "48335": ("Mitchell", 32.3041, -100.9244),
    "48337": ("Montague", 33.6784, -97.7250), "48339": ("Montgomery", 30.2988, -95.5029),
    "48341": ("Moore", 35.8357, -101.8905), "48343": ("Morris", 33.1165, -94.7313),
    "48345": ("Motley", 34.0579, -100.7932), "48347": ("Nacogdoches", 31.6206, -94.6202),
    "48349": ("Navarro", 32.0484, -96.4769), "48351": ("Newton", 30.7867, -93.7392),
    "48353": ("Nolan", 32.3123, -100.4181), "48355": ("Nueces", 27.7400, -97.5162),
    "48357": ("Ochiltree", 36.2787, -100.8159), "48359": ("Oldham", 35.4019, -102.5976),
    "48361": ("Orange", 30.1223, -93.8941), "48363": ("Palo Pinto", 32.7522, -98.3180),
    "48365": ("Panola", 32.1640, -94.3052), "48367": ("Parker", 32.7771, -97.8059),
    "48369": ("Parmer", 34.5322, -102.7849), "48371": ("Pecos", 30.7733, -102.7182),
    "48373": ("Polk", 30.7846, -94.8373), "48375": ("Potter", 35.3987, -101.8938),
    "48377": ("Presidio", 30.0059, -104.2616), "48379": ("Rains", 32.8705, -95.7956),
    "48381": ("Randall", 34.9625, -101.8955), "48383": ("Reagan", 31.3752, -101.5144),
    "48385": ("Real", 29.8301, -99.8125), "48387": ("Red River", 33.6196, -95.0484),
    "48389": ("Reeves", 31.3084, -103.7127), "48391": ("Refugio", 28.3221, -97.1625),
    "48393": ("Roberts", 35.8386, -100.8367), "48395": ("Robertson", 31.0255, -96.5149),
    "48397": ("Rockwall", 32.8999, -96.4120), "48399": ("Runnels", 31.8451, -99.9827),
    "48401": ("Rusk", 32.1094, -94.7564), "48403": ("Sabine", 31.3433, -93.8519),
    "48405": ("San Augustine", 31.3824, -94.1632), "48407": ("San Jacinto", 30.5744, -95.1631),
    "48409": ("San Patricio", 28.0118, -97.5172), "48411": ("San Saba", 31.1551, -98.8193),
    "48413": ("Schleicher", 30.8962, -100.5272), "48415": ("Scurry", 32.7444, -100.9133),
    "48417": ("Shackelford", 32.7438, -99.3470), "48419": ("Shelby", 31.7901, -94.1426),
    "48421": ("Sherman", 36.2786, -101.8993), "48423": ("Smith", 32.3751, -95.2689),
    "48425": ("Somervell", 32.2181, -97.7692), "48427": ("Starr", 26.5309, -98.7402),
    "48429": ("Stephens", 32.7381, -98.8393), "48431": ("Sterling", 31.8358, -101.0549),
    "48433": ("Stonewall", 33.1796, -100.2538), "48435": ("Sutton", 30.5222, -100.5134),
    "48437": ("Swisher", 34.5263, -101.7439), "48439": ("Tarrant", 32.7721, -97.2912),
    "48441": ("Taylor", 32.2971, -99.8904), "48443": ("Terrell", 30.2323, -102.0725),
    "48445": ("Terry", 33.1712, -102.3393), "48447": ("Throckmorton", 33.1707, -99.2058),
    "48449": ("Titus", 33.2146, -94.9668), "48451": ("Tom Green", 31.3983, -100.4638),
    "48453": ("Travis", 30.2395, -97.6913), "48455": ("Trinity", 31.0967, -95.1517),
    "48457": ("Tyler", 30.7693, -94.3757), "48459": ("Upshur", 32.7353, -94.9412),
    "48461": ("Upton", 31.3538, -102.0415), "48463": ("Uvalde", 29.3503, -99.7684),
    "48465": ("Val Verde", 29.8753, -101.1433), "48467": ("Van Zandt", 32.5588, -95.8369),
    "48469": ("Victoria", 28.7964, -96.9712), "48471": ("Walker", 30.7432, -95.5698),
    "48473": ("Waller", 30.0136, -95.9821), "48475": ("Ward", 31.5131, -103.1051),
    "48477": ("Washington", 30.2151, -96.4103), "48479": ("Webb", 27.7608, -99.3408),
    "48481": ("Wharton", 29.2785, -96.2297), "48483": ("Wheeler", 35.3926, -100.2531),
    "48485": ("Wichita", 33.9882, -98.7080), "48487": ("Wilbarger", 34.0849, -99.2424),
    "48489": ("Willacy", 26.4819, -97.5947), "48491": ("Williamson", 30.6491, -97.6051),
    "48493": ("Wilson", 29.1739, -98.0867), "48495": ("Winkler", 31.8329, -103.0549),
    "48497": ("Wise", 33.2193, -97.6530), "48499": ("Wood", 32.7836, -95.3822),
    "48501": ("Yoakum", 33.1623, -102.8322), "48503": ("Young", 33.1588, -98.6784),
    "48505": ("Zapata", 26.9970, -99.1826), "48507": ("Zavala", 28.8647, -99.7598),
}

# Priority-MSA core counties named in the RLSB business plan (a subset used for
# emphasis; the working footprint is now the whole state above).
PRIORITY_MSA = {
    "Midland": "48329", "Ector": "48135", "Taylor": "48441",
    "Smith": "48423", "Tom Green": "48451", "Dallas": "48113", "Tarrant": "48439",
}

FOOTPRINT_UPPER = {name.upper(): fips for name, fips in FOOTPRINT.items()}
FOOTPRINT_FIPS = set(FOOTPRINT.values())


def in_footprint(county_name):
    """True for any Texas county (the footprint is the whole state)."""
    if not county_name:
        return False
    return county_name.strip().upper() in FOOTPRINT_UPPER


def county_geo(fips):
    """(name, lat, lng) for a 5-digit county FIPS, or (fips, None, None)."""
    return COUNTY_GEO.get(fips, (fips, None, None))


def http_get(url, headers=None, timeout=45, retries=4, backoff=2.0):
    """GET raw bytes with a shared UA and simple exponential-ish backoff."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last


def http_get_json(url, headers=None, timeout=45, retries=4):
    return json.loads(http_get(url, headers=headers, timeout=timeout, retries=retries))


DATA_START = "/*__DATA_START__*/"
DATA_END = "/*__DATA_END__*/"


def inject_data(html_path, data_obj):
    """Replace the JSON between the DATA markers in a self-contained dashboard."""
    path = Path(html_path)
    html = path.read_text(encoding="utf-8")
    payload = json.dumps(data_obj, separators=(",", ":"), ensure_ascii=False)
    pattern = re.compile(re.escape(DATA_START) + r".*?" + re.escape(DATA_END), re.S)
    if not pattern.search(html):
        raise SystemExit("data markers (%s ... %s) not found in %s"
                         % (DATA_START, DATA_END, html_path))
    path.write_text(pattern.sub(DATA_START + payload + DATA_END, html, count=1),
                    encoding="utf-8")
    return len(payload)


def stamp(source, extra=None):
    """Standard freshness/provenance block embedded with every dashboard's data."""
    block = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
    }
    if extra:
        block.update(extra)
    return block


# ---------------------------------------------------------- West Texas ----
# v1 scope for the Competitor Terms dashboard: the Permian Basin, South Plains,
# Panhandle, Concho Valley, Big Bend and far West. County -> 5-digit FIPS.
WEST_TEXAS = {
    "Andrews": "48003", "Archer": "48009", "Armstrong": "48011", "Bailey": "48017",
    "Baylor": "48023", "Borden": "48033", "Brewster": "48043", "Briscoe": "48045",
    "Callahan": "48059", "Carson": "48065", "Castro": "48069", "Childress": "48075",
    "Clay": "48077", "Cochran": "48079", "Coke": "48081", "Coleman": "48083",
    "Collingsworth": "48087", "Concho": "48095", "Cottle": "48101", "Crane": "48103",
    "Crockett": "48105", "Crosby": "48107", "Culberson": "48109", "Dallam": "48111",
    "Dawson": "48115", "Deaf Smith": "48117", "Dickens": "48125", "Donley": "48129",
    "Ector": "48135", "El Paso": "48141", "Fisher": "48151", "Floyd": "48153",
    "Foard": "48155", "Gaines": "48165", "Garza": "48169", "Glasscock": "48173",
    "Gray": "48179", "Hale": "48189", "Hall": "48191", "Hansford": "48195",
    "Hardeman": "48197", "Hartley": "48205", "Haskell": "48207", "Hemphill": "48211",
    "Hockley": "48219", "Howard": "48227", "Hudspeth": "48229", "Hutchinson": "48233",
    "Irion": "48235", "Jeff Davis": "48243", "Jones": "48253", "Kent": "48263",
    "Kimble": "48267", "King": "48269", "Knox": "48275", "Lamb": "48279",
    "Lipscomb": "48295", "Loving": "48301", "Lubbock": "48303", "Lynn": "48305",
    "Martin": "48317", "Mason": "48319", "McCulloch": "48307", "Menard": "48327",
    "Midland": "48329", "Mitchell": "48335", "Moore": "48341", "Motley": "48345",
    "Nolan": "48353", "Ochiltree": "48357", "Oldham": "48359", "Parmer": "48369",
    "Pecos": "48371", "Potter": "48375", "Presidio": "48377", "Randall": "48381",
    "Reagan": "48383", "Reeves": "48389", "Roberts": "48393", "Runnels": "48399",
    "Schleicher": "48413", "Scurry": "48415", "Shackelford": "48417", "Sherman": "48421",
    "Sterling": "48431", "Stonewall": "48433", "Sutton": "48435", "Swisher": "48437",
    "Taylor": "48441", "Terrell": "48443", "Terry": "48445", "Throckmorton": "48447",
    "Tom Green": "48451", "Upton": "48461", "Val Verde": "48465", "Ward": "48475",
    "Wheeler": "48483", "Wichita": "48485", "Wilbarger": "48487", "Winkler": "48495",
    "Yoakum": "48501",
}

# County -> market (CBSA metro/micro core, or the rural bucket).
WEST_TEXAS_MARKET = {
    "Andrews": "Andrews", "Archer": "Wichita Falls", "Armstrong": "Amarillo",
    "Bailey": "Rural West Texas", "Baylor": "Rural West Texas", "Borden": "Rural West Texas",
    "Brewster": "Alpine", "Briscoe": "Rural West Texas", "Callahan": "Abilene",
    "Carson": "Amarillo", "Castro": "Rural West Texas", "Childress": "Rural West Texas",
    "Clay": "Wichita Falls", "Cochran": "Rural West Texas", "Coke": "Rural West Texas",
    "Coleman": "Rural West Texas", "Collingsworth": "Rural West Texas", "Concho": "Rural West Texas",
    "Cottle": "Rural West Texas", "Crane": "Rural West Texas", "Crockett": "Rural West Texas",
    "Crosby": "Lubbock", "Culberson": "Rural West Texas", "Dallam": "Rural West Texas",
    "Dawson": "Lamesa", "Deaf Smith": "Hereford", "Dickens": "Rural West Texas",
    "Donley": "Rural West Texas", "Ector": "Odessa", "El Paso": "El Paso",
    "Fisher": "Rural West Texas", "Floyd": "Rural West Texas", "Foard": "Rural West Texas",
    "Gaines": "Rural West Texas", "Garza": "Rural West Texas", "Glasscock": "Rural West Texas",
    "Gray": "Pampa", "Hale": "Plainview", "Hall": "Rural West Texas",
    "Hansford": "Rural West Texas", "Hardeman": "Rural West Texas", "Hartley": "Rural West Texas",
    "Haskell": "Rural West Texas", "Hemphill": "Rural West Texas", "Hockley": "Levelland",
    "Howard": "Big Spring", "Hudspeth": "El Paso", "Hutchinson": "Borger",
    "Irion": "San Angelo", "Jeff Davis": "Rural West Texas", "Jones": "Abilene",
    "Kent": "Rural West Texas", "Kimble": "Rural West Texas", "King": "Rural West Texas",
    "Knox": "Rural West Texas", "Lamb": "Rural West Texas", "Lipscomb": "Rural West Texas",
    "Loving": "Rural West Texas", "Lubbock": "Lubbock", "Lynn": "Lubbock",
    "Martin": "Midland", "Mason": "Rural West Texas", "McCulloch": "Rural West Texas",
    "Menard": "Rural West Texas", "Midland": "Midland", "Mitchell": "Rural West Texas",
    "Moore": "Dumas", "Motley": "Rural West Texas", "Nolan": "Sweetwater",
    "Ochiltree": "Rural West Texas", "Oldham": "Amarillo", "Parmer": "Rural West Texas",
    "Pecos": "Fort Stockton", "Potter": "Amarillo", "Presidio": "Rural West Texas",
    "Randall": "Amarillo", "Reagan": "Rural West Texas", "Reeves": "Pecos (Reeves)",
    "Roberts": "Rural West Texas", "Runnels": "Rural West Texas", "Schleicher": "Rural West Texas",
    "Scurry": "Snyder", "Shackelford": "Rural West Texas", "Sherman": "Rural West Texas",
    "Sterling": "San Angelo", "Stonewall": "Rural West Texas", "Sutton": "Rural West Texas",
    "Swisher": "Rural West Texas", "Taylor": "Abilene", "Terrell": "Rural West Texas",
    "Terry": "Rural West Texas", "Throckmorton": "Rural West Texas", "Tom Green": "San Angelo",
    "Upton": "Rural West Texas", "Val Verde": "Del Rio", "Ward": "Rural West Texas",
    "Wheeler": "Rural West Texas", "Wichita": "Wichita Falls", "Wilbarger": "Rural West Texas",
    "Winkler": "Rural West Texas", "Yoakum": "Rural West Texas",
}
