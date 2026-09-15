const fs = require('fs');
const path = require('path');
const { pathToFileURL, fileURLToPath } = require('url');
const { Runtime, FixedConnectionMap } = require('@malloydata/malloy');
const { DuckDBConnection } = require('@malloydata/db-duckdb');
const { BigQueryConnection } = require('@malloydata/db-bigquery');

// Custom URL Reader handling URL objects and file:// URI strings
class FileURLReader {
  async readURL(url) {
    const filePath = typeof url === 'string' ? fileURLToPath(url) : fileURLToPath(url.href);
    if (!fs.existsSync(filePath)) {
      throw new Error(`File not found: ${filePath}`);
    }
    const contents = await fs.promises.readFile(filePath, 'utf8');
    return contents;
  }
}

function cleanComment(f) {
  const textArr = f.annotations ? f.annotations.texts() : [];
  const rawComments = textArr
    .map(t => t.replace(/^#\([^)]*\)\s*\"?|\"?\s*$/g, '').trim())
    .filter(Boolean);
  const comment = Array.from(new Set(rawComments)).join(' ');
  return comment.replace(/\|/g, '\\|').replace(/\r?\n/g, ' ').trim();
}

function extractExploreData(explore) {
  const directFields = [];
  const joinedEntities = {};
  const allFields = [];

  for (const f of explore.allFields) {
    if (f.isExploreField()) {
      if (f.name.endsWith('_raw')) continue;
      const entityName = f.name;
      const childFields = [];

      function extractChildFields(childExplore, prefix) {
        if (!childExplore.allFields) return;
        for (const cf of childExplore.allFields) {
          if (cf.name.endsWith('_raw')) continue;
          const fullName = `${prefix}.${cf.name}`;
          if (cf.isExploreField()) {
            extractChildFields(cf, fullName);
          } else {
            let type = cf.isAtomicField() ? cf.type : 'query';
            let category = cf.isQueryField() ? 'measure' : (cf.isAtomicField() && cf.isCalculation() ? 'measure' : 'dimension');
            const item = {
              name: fullName,
              type,
              expressionType: category,
              category,
              comment: cleanComment(cf)
            };
            childFields.push(item);
            allFields.push(item);
          }
        }
      }

      extractChildFields(f, entityName);
      joinedEntities[entityName] = {
        name: entityName,
        fields: childFields
      };
    } else {
      // Do not treat private or un-included composite fields as public root fields
      if ((f.fieldTypeDef && f.fieldTypeDef.accessModifier === 'private') || f.accessModifier === 'private') {
        continue;
      }
      let type = f.isAtomicField() ? f.type : 'query';
      let category = f.isQueryField() ? 'measure' : (f.isAtomicField() && f.isCalculation() ? 'measure' : 'dimension');
      const item = {
        name: f.name,
        type,
        expressionType: category,
        category,
        comment: cleanComment(f)
      };
      directFields.push(item);
      allFields.push(item);
    }
  }

  let pk = null;
  if (typeof explore.primaryKey === 'string') {
    pk = explore.primaryKey;
  } else if (explore.primaryKey && explore.primaryKey.name) {
    pk = explore.primaryKey.name;
  } else if (Array.isArray(explore.primaryKey)) {
    pk = explore.primaryKey.map(p => (typeof p === 'string' ? p : (p && p.name ? p.name : String(p)))).join(', ');
  }

  return {
    name: explore.name,
    dialect: (explore.structDef && explore.structDef.dialect) ? explore.structDef.dialect : 'duckdb',
    primary_key: pk,
    direct_fields: directFields,
    joined_entities: joinedEntities,
    fields: allFields
  };
}

async function compileMalloyFile(filePath) {
  const absolutePath = path.resolve(filePath);
  const fileURL = pathToFileURL(absolutePath);

  // 1. Initialize Connections
  let dir = path.dirname(absolutePath);
  let packageDir = dir;
  while (dir !== path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, 'publisher.json')) || fs.existsSync(path.join(dir, '1_raw_views'))) {
      packageDir = dir;
      break;
    }
    dir = path.dirname(dir);
  }

  const duckdbConn = new DuckDBConnection('duckdb', undefined, packageDir);
  const bigqueryConn = new BigQueryConnection('bigquery');

  const connectionMap = new FixedConnectionMap(
    new Map([
      ['duckdb', duckdbConn],
      ['bigquery', bigqueryConn]
    ]),
    'duckdb'
  );

  // 2. Instantiate Runtime with Custom File Reader
  const urlReader = new FileURLReader();
  const runtime = new Runtime({ urlReader, connections: connectionMap });

  // 3. Load & Compile Model using URL Object
  const modelMaterializer = runtime.loadModel(fileURL);
  const model = await modelMaterializer.getModel();

  // 4. Extract AST / Structural Metadata
  const exploresToProcess = (model.exportedExplores && model.exportedExplores.length > 0)
    ? model.exportedExplores
    : model.explores;

  const sources = {};
  for (const explore of exploresToProcess) {
    if (explore.name.endsWith('_raw')) continue;
    sources[explore.name] = extractExploreData(explore);
  }

  return sources;
}

async function main() {
  const targetFile = process.argv[2];

  if (!targetFile) {
    console.error(JSON.stringify({ error: "No target file path provided to compile_malloy.js" }));
    process.exit(1);
  }

  try {
    const astData = await compileMalloyFile(targetFile);
    // ONLY output JSON to stdout so python can parse it cleanly
    process.stdout.write(JSON.stringify(astData) + '\n');
  } catch (error) {
    console.error(JSON.stringify({ 
      error: error.message || String(error),
      stack: error.stack 
    }));
    process.exit(1);
  }
}

main();