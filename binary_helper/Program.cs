using System.Text.Json;
using System.Text.RegularExpressions;
using CodeWalker.GameFiles;
using CodeWalker.Utils;

internal sealed class RenameOperation
{
    public string Type { get; set; } = "";
    public string Input { get; set; } = "";
    public string Output { get; set; } = "";
    public string Kind { get; set; } = "";
    public int OldSlot { get; set; }
    public int NewSlot { get; set; }
    public string OldDrawableName { get; set; } = "";
    public string NewDrawableName { get; set; } = "";
}

internal sealed class RewriteResult
{
    public string File { get; set; } = "";
    public int DrawableNames { get; set; }
    public int TextureNames { get; set; }
}

internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        if (args.Length != 1 || !File.Exists(args[0]))
        {
            Console.Error.WriteLine("Usage: ClothFixer.Binary <operations.json>");
            return 2;
        }

        try
        {
            var operations = JsonSerializer.Deserialize<List<RenameOperation>>(
                await File.ReadAllTextAsync(args[0]),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true }) ?? [];

            var results = new List<RewriteResult>();
            foreach (var operation in operations)
            {
                if (!File.Exists(operation.Input))
                    throw new FileNotFoundException("Input asset not found", operation.Input);
                if (operation.NewSlot == operation.OldSlot)
                    throw new InvalidOperationException("A rewrite operation has identical old and new slots.");

                RewriteResult result = operation.Type.ToLowerInvariant() switch
                {
                    "ydd" => await RewriteYdd(operation),
                    "ytd" => await RewriteYtd(operation),
                    _ => throw new InvalidOperationException($"Unsupported asset type: {operation.Type}")
                };
                results.Add(result);
            }

            Console.WriteLine(JsonSerializer.Serialize(results, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
    }

    private static async Task<RewriteResult> RewriteYdd(RenameOperation operation)
    {
        var bytes = await File.ReadAllBytesAsync(operation.Input);
        var ydd = new YddFile();
        await ydd.LoadAsync(bytes);

        var drawables = ydd.DrawableDict?.Drawables?.data_items ?? ydd.Drawables ?? throw new InvalidDataException("YDD has no drawable array.");
        if (drawables.Length == 0)
            throw new InvalidDataException("YDD contains no drawables.");

        var drawableCount = 0;
        var textureCount = 0;
        var hashes = ydd.DrawableDict?.Hashes;

        for (var index = 0; index < drawables.Length; index++)
        {
            var drawable = drawables[index];
            if (drawable == null)
                continue;

            var unresolvedName = string.IsNullOrWhiteSpace(drawable.Name) ||
                                 drawable.Name.EndsWith("#dd", StringComparison.OrdinalIgnoreCase);
            var renamedDrawable = unresolvedName
                ? (drawables.Length == 1 ? operation.NewDrawableName : drawable.Name)
                : ReplaceSlot(drawable.Name, operation.OldSlot, operation.NewSlot);

            if (unresolvedName && drawables.Length > 1)
                throw new InvalidDataException("Drawable names are unresolved in a multi-drawable YDD; refusing to guess which entry to rename.");

            if (!string.IsNullOrEmpty(renamedDrawable) &&
                !string.Equals(renamedDrawable, drawable.Name, StringComparison.Ordinal))
            {
                drawable.Name = renamedDrawable;
                if (hashes != null && index < hashes.Length)
                    hashes[index] = JenkHash.GenHash(renamedDrawable.ToLowerInvariant());
                drawableCount++;
            }

            var dictionary = drawable.ShaderGroup?.TextureDictionary;
            var textureItems = dictionary?.Textures?.data_items;
            var renamedHashes = new Dictionary<uint, string>();
            var dictionaryNeedsRebuild = false;
            var shaders = drawable.ShaderGroup?.Shaders?.data_items;

            // Some YDDs store embedded normal/specular textures directly in shader parameters.
            // Rename those objects too, even when they are not listed in TextureDictionary.
            if (shaders != null)
            {
                foreach (var shader in shaders)
                {
                    var parameters = shader?.ParametersList?.Parameters;
                    if (parameters == null)
                        continue;

                    foreach (var parameter in parameters)
                    {
                        if (parameter?.Data is not Texture embeddedTexture ||
                            string.IsNullOrEmpty(embeddedTexture.Name))
                            continue;

                        var oldHash = embeddedTexture.NameHash;
                        var renamedTexture = ReplaceSlot(embeddedTexture.Name, operation.OldSlot, operation.NewSlot);
                        if (string.Equals(renamedTexture, embeddedTexture.Name, StringComparison.Ordinal))
                            continue;

                        embeddedTexture.Name = renamedTexture;
                        embeddedTexture.NameHash = JenkHash.GenHash(renamedTexture.ToLowerInvariant());
                        renamedHashes[oldHash] = renamedTexture;
                        textureCount++;
                        dictionaryNeedsRebuild = true;
                    }
                }
            }

            if (textureItems != null)
            {
                foreach (var texture in textureItems)
                {
                    if (texture == null || string.IsNullOrEmpty(texture.Name))
                        continue;

                    var oldHash = texture.NameHash;
                    var renamedTexture = ReplaceSlot(texture.Name, operation.OldSlot, operation.NewSlot);
                    if (string.Equals(renamedTexture, texture.Name, StringComparison.Ordinal))
                        continue;

                    texture.Name = renamedTexture;
                    texture.NameHash = JenkHash.GenHash(renamedTexture.ToLowerInvariant());
                    renamedHashes[oldHash] = renamedTexture;
                    textureCount++;
                    dictionaryNeedsRebuild = true;
                }
            }

            if (renamedHashes.Count > 0 && shaders != null)
            {
                foreach (var shader in shaders)
                {
                    var parameters = shader?.ParametersList?.Parameters;
                    if (parameters == null)
                        continue;

                    foreach (var parameter in parameters)
                    {
                        if (parameter?.Data is TextureBase textureReference &&
                            parameter.Data is not Texture &&
                            renamedHashes.TryGetValue(textureReference.NameHash, out var newTextureName))
                        {
                            textureReference.Name = newTextureName;
                            textureReference.NameHash = JenkHash.GenHash(newTextureName.ToLowerInvariant());
                        }
                    }
                }
            }

            if (dictionary != null && textureItems != null && dictionaryNeedsRebuild)
                dictionary.BuildFromTextureList(textureItems.Where(x => x != null).ToList());
        }

        var output = drawableCount == 0 && textureCount == 0 ? bytes : ydd.Save();
        if (drawableCount > 0 || textureCount > 0)
        {
            var verification = new YddFile();
            await verification.LoadAsync(output);
            if (verification.DrawableDict?.Drawables?.data_items?.Length != drawables.Length)
                throw new InvalidDataException("Rewritten YDD failed its round-trip validation.");
        }

        Directory.CreateDirectory(Path.GetDirectoryName(operation.Output)!);
        await File.WriteAllBytesAsync(operation.Output, output);
        return new RewriteResult { File = operation.Input, DrawableNames = drawableCount, TextureNames = textureCount };
    }

    private static async Task<RewriteResult> RewriteYtd(RenameOperation operation)
    {
        var bytes = await File.ReadAllBytesAsync(operation.Input);
        var ytd = new YtdFile();
        await ytd.LoadAsync(bytes);

        var dictionary = ytd.TextureDict ?? throw new InvalidDataException("YTD has no texture dictionary.");
        var textureItems = dictionary.Textures?.data_items ?? throw new InvalidDataException("YTD has no texture entries.");
        var textureCount = 0;

        foreach (var texture in textureItems)
        {
            if (texture == null || string.IsNullOrEmpty(texture.Name))
                continue;

            var renamed = ReplaceSlot(texture.Name, operation.OldSlot, operation.NewSlot);
            if (string.Equals(renamed, texture.Name, StringComparison.Ordinal))
                continue;

            texture.Name = renamed;
            texture.NameHash = JenkHash.GenHash(renamed.ToLowerInvariant());
            textureCount++;
        }

        var output = textureCount == 0 ? bytes : SaveYtd(ytd, textureItems);
        if (textureCount > 0)
        {
            var verification = new YtdFile();
            await verification.LoadAsync(output);
            if (verification.TextureDict?.Textures?.data_items?.Length != textureItems.Length)
                throw new InvalidDataException("Rewritten YTD failed its round-trip validation.");
        }

        Directory.CreateDirectory(Path.GetDirectoryName(operation.Output)!);
        await File.WriteAllBytesAsync(operation.Output, output);
        return new RewriteResult { File = operation.Input, TextureNames = textureCount };
    }

    private static byte[] SaveYtd(YtdFile ytd, Texture[] textures)
    {
        ytd.TextureDict!.BuildFromTextureList(textures.Where(x => x != null).ToList());
        return ytd.Save();
    }

    private static string ReplaceSlot(string? name, int oldSlot, int newSlot)
    {
        if (string.IsNullOrEmpty(name))
            return name ?? string.Empty;

        var oldValue = oldSlot.ToString("D3");
        var newValue = newSlot.ToString("D3");
        var pattern = $"(?<![0-9]){Regex.Escape(oldValue)}(?![0-9])";
        return Regex.Replace(name, pattern, newValue, RegexOptions.CultureInvariant);
    }
}
