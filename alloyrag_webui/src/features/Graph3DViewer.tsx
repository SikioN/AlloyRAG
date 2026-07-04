import React from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import { UndirectedGraph } from 'graphology';
import * as THREE from 'three'; // Import THREE

interface Graph3DViewerProps {
  graph: UndirectedGraph | null;
}

const Graph3DViewer: React.FC<Graph3DViewerProps> = ({ graph }) => {
  if (!graph) {
    return null;
  }

  const convertGraphologyToReactForceGraph = (graphologyGraph: UndirectedGraph) => {
    const nodes = graphologyGraph.nodes().map(nodeId => {
      const attrs = graphologyGraph.getNodeAttributes(nodeId);
      return { id: nodeId, ...attrs };
    });

    const links = graphologyGraph.edges().map(edgeId => {
      const [source, target] = graphologyGraph.extremities(edgeId);
      const attrs = graphologyGraph.getEdgeAttributes(edgeId);
      return { source, target, ...attrs };
    });

    return { nodes, links };
  };

  const graphData = convertGraphologyToReactForceGraph(graph);

  return (
    <ForceGraph3D
      graphData={graphData}
      nodeLabel="label"
      nodeAutoColorBy="type"
      // Add nodeThreeObjectExtend to allow combining base objects with custom ones
      nodeThreeObjectExtend={true}
      nodeThreeObject={node => {
        // Create a sphere for the node
        const sphere = new THREE.Mesh(
          new THREE.SphereGeometry(node.size/2 || 5), // Use node.size or a default
          new THREE.MeshLambertMaterial({ color: (node.color as string) || 'white', transparent: true, opacity: 0.75 })
        );

        // Create the sprite text for the label
        const sprite = new SpriteText(node.label as string);
        sprite.color = node.color as string || 'white';
        sprite.textHeight = 8;
        // Position the label relative to the sphere.
        // Example from documentation: sprite.center.y = -0.6; // shift above node
        // We might need to adjust this later for better positioning.
        sprite.position.z = (node.size || 5) + 4; // Roughly above the sphere
        // Add the sprite as a child of the sphere, so they move together
        sphere.add(sprite);

        return sphere;
      }}
    />
  );
};

export default Graph3DViewer;
