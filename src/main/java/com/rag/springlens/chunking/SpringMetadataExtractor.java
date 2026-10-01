package com.rag.springlens.chunking;

import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SpringMetadataExtractor {

    public enum ArchitecturalLayer {
        WEB_PRESENTATION,
        BUSINESS_SERVICE,
        DATA_PERSISTENCE,
        CONFIG_INFRASTRUCTURE,
        DOMAIN_MODEL,
        GENERAL_COMPONENT
    }

    public static Map<String, Object> extractClassMetadata(ClassOrInterfaceDeclaration classDecl, String fileName) {
        Map<String, Object> metadata = new HashMap<>();

        List<String> annotations = classDecl.getAnnotations().stream()
                .map(AnnotationExpr::getNameAsString)
                .collect(Collectors.toList());

        ArchitecturalLayer layer = inferArchitecturalLayer(annotations, fileName);
        List<String> dependencies = extractDependencies(classDecl);

        //capture implemented interfaces and extended superclass/superinterface
        List<String> implementedInterfaces = classDecl.getImplementedTypes().stream()
                .map(ClassOrInterfaceType::getNameAsString)
                .collect(Collectors.toList());
        List<String> extendedTypes = classDecl.getExtendedTypes().stream()
                .map(ClassOrInterfaceType::getNameAsString)
                .collect(Collectors.toList());

        metadata.put("fileName", fileName);
        metadata.put("className", classDecl.getNameAsString());
        metadata.put("annotations", annotations);
        metadata.put("architecturalLayer", layer.name());
        metadata.put("dependencies", dependencies);
        metadata.put("implementedInterfaces", implementedInterfaces);
        metadata.put("extendedTypes", extendedTypes);

        return metadata;
    }

    public static ArchitecturalLayer inferArchitecturalLayer(List<String> annotations, String fileName) {
        for (String ann : annotations) {
            if (ann.equals("RestController") || ann.equals("Controller")) {
                return ArchitecturalLayer.WEB_PRESENTATION;
            }
            if (ann.equals("Service")) {
                return ArchitecturalLayer.BUSINESS_SERVICE;
            }
            if (ann.equals("Repository") || ann.equals("Entity") || ann.equals("Table")) {
                return ArchitecturalLayer.DATA_PERSISTENCE;
            }
            if (ann.equals("Configuration") || ann.equals("SpringBootApplication")) {
                return ArchitecturalLayer.CONFIG_INFRASTRUCTURE;
            }
        }

        if (fileName.contains("Controller")) return ArchitecturalLayer.WEB_PRESENTATION;
        if (fileName.contains("Service") || fileName.contains("Validator")) return ArchitecturalLayer.BUSINESS_SERVICE;
        if (fileName.contains("Repository") || fileName.contains("Entity")) return ArchitecturalLayer.DATA_PERSISTENCE;
        if (fileName.contains("Config")) return ArchitecturalLayer.CONFIG_INFRASTRUCTURE;

        return ArchitecturalLayer.GENERAL_COMPONENT;
    }

    public static List<String> extractDependencies(ClassOrInterfaceDeclaration classDecl) {
        List<String> dependencies = new ArrayList<>();

        for (FieldDeclaration field : classDecl.getFields()) {
            boolean isAutowired = field.getAnnotations().stream()
                    .anyMatch(a -> a.getNameAsString().equals("Autowired") || a.getNameAsString().equals("Resource"));
            boolean isFinal = field.isFinal();

            if (isAutowired || isFinal) {
                field.getVariables().forEach(v -> dependencies.add(v.getTypeAsString() + " " + v.getNameAsString()));
            }
        }

        for (ConstructorDeclaration constructor : classDecl.getConstructors()) {
            constructor.getParameters().forEach(p -> {
                String dep = p.getTypeAsString() + " " + p.getNameAsString();
                if (!dependencies.contains(dep)) {
                    dependencies.add(dep);
                }
            });
        }

        return dependencies;
    }

    public static String buildHeader(Map<String, Object> metadata, String unitType, String unitName) {
        StringBuilder sb = new StringBuilder();
        sb.append("=== [SPRING ARCHITECTURAL METADATA] ===\n");
        sb.append("File: ").append(metadata.get("fileName")).append("\n");
        sb.append("Class: ").append(metadata.get("className")).append("\n");
        sb.append("Architectural Layer: ").append(metadata.get("architecturalLayer")).append("\n");
        sb.append("Stereotype Annotations: ").append(metadata.get("annotations")).append("\n");
        sb.append("Implements: ").append(metadata.get("implementedInterfaces")).append("\n");
        sb.append("Extends: ").append(metadata.get("extendedTypes")).append("\n");
        sb.append("Injected Dependencies: ").append(metadata.get("dependencies")).append("\n");
        sb.append("Unit Granularity: ").append(unitType).append(" [").append(unitName).append("]\n");
        sb.append("======================================\n\n");
        return sb.toString();
    }
}